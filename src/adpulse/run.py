"""End-to-end orchestrator: one command runs the whole AdPulse project.

    python -m adpulse.run --scale full      # ~2M rows, produces committed metrics.json
    python -m adpulse.run --scale ci        # ~20k rows, fast smoke run (used by CI)

Steps: generate -> Spark pipeline -> anomaly detection -> segmentation -> A/B test ->
load SQLite -> Excel report -> Power BI star schema -> write metrics.json.

Every number written to metrics.json comes from THIS run; nothing is hand-entered.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime

import pandas as pd

from . import (
    ab_test,
    anomaly,
    generate_data,
    kpis,
    load_db,
    report_excel,
    segmentation,
    spark_pipeline,
    star_schema,
)
from . import config as C


def _channel_rollup(crm: pd.DataFrame) -> pd.DataFrame:
    """Roll channel x region x month KPIs up to one row per channel (ratios recomputed)."""
    agg = crm.groupby("channel", as_index=False)[
        ["impressions", "clicks", "conversions", "spend", "revenue"]
    ].sum()
    k = agg.apply(
        lambda r: kpis.all_kpis(r.impressions, r.clicks, r.conversions, r.spend, r.revenue),
        axis=1,
        result_type="expand",
    )
    out = pd.concat([agg, k], axis=1)
    out[["spend", "revenue"]] = out[["spend", "revenue"]].round(2)
    out[["ctr", "cvr"]] = out[["ctr", "cvr"]].round(6)
    out[["cpc", "cpa", "roas"]] = out[["cpc", "cpa", "roas"]].round(4)
    return out.sort_values("spend", ascending=False).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full AdPulse pipeline.")
    parser.add_argument("--scale", choices=["full", "ci"], default=None)
    parser.add_argument("--skip-generate", action="store_true", help="Reuse existing raw data.")
    parser.add_argument("--db-target", choices=["sqlite", "postgres"], default="sqlite")
    parser.add_argument("--metrics-out", default=str(C.METRICS_PATH))
    args = parser.parse_args()

    scale = C.resolve_scale(args.scale)
    C.ensure_dirs()
    t0 = datetime.now(UTC)

    # 1) Generate synthetic data -----------------------------------------------------
    if args.skip_generate:
        gen_counts = {"note": "reused existing raw data"}
    else:
        print(f"[1/8] generating synthetic data (scale={args.scale or 'env/full'}) ...")
        gen_counts = generate_data.generate(scale)

    # 2) Spark pipeline --------------------------------------------------------------
    print("[2/8] running Spark pipeline (clean + KPIs) ...")
    pipe = spark_pipeline.run_pipeline()

    crm = pd.read_csv(C.OUTPUT_DIR / "kpi_channel_region_month.csv")
    cam = pd.read_csv(C.OUTPUT_DIR / "kpi_campaign_month.csv")
    daily = pd.read_csv(C.OUTPUT_DIR / "daily_campaign.csv", parse_dates=["date"])

    # 3) Anomaly detection -----------------------------------------------------------
    print("[3/8] detecting anomalies ...")
    anomalies = anomaly.detect_anomalies(daily)
    anomalies.to_csv(C.OUTPUT_DIR / "anomalies.csv", index=False)

    # 4) Segmentation ----------------------------------------------------------------
    print("[4/8] segmenting customers (RFM + K-Means) ...")
    customers = pd.read_csv(C.RAW_CUSTOMERS_CSV)
    transactions = pd.read_csv(C.RAW_TRANSACTIONS_CSV)
    seg = segmentation.run_segmentation(transactions, customers, C.AS_OF_DATE)
    seg.rfm.to_csv(C.OUTPUT_DIR / "customer_segments.csv", index=False)
    seg.profiles.to_csv(C.OUTPUT_DIR / "segment_profiles.csv", index=False)
    seg.k_scores.to_csv(C.OUTPUT_DIR / "k_selection.csv", index=False)
    segmentation.save_k_plot(seg.k_scores, C.ASSETS_DIR / "segmentation_k.png")

    # 5) A/B test --------------------------------------------------------------------
    print("[5/8] running A/B test ...")
    ab_counts = pd.read_csv(C.OUTPUT_DIR / "ab_counts.csv").set_index("creative")
    a, b = "creative_A", "creative_B"
    result = ab_test.two_proportion_ztest(
        conv_a=int(ab_counts.loc[a, "conversions"]), n_a=int(ab_counts.loc[a, "clicks"]),
        conv_b=int(ab_counts.loc[b, "conversions"]), n_b=int(ab_counts.loc[b, "clicks"]),
    )
    chi = ab_test.chi_square_test(
        conv_a=int(ab_counts.loc[a, "conversions"]), n_a=int(ab_counts.loc[a, "clicks"]),
        conv_b=int(ab_counts.loc[b, "conversions"]), n_b=int(ab_counts.loc[b, "clicks"]),
    )
    power = ab_test.observed_power(result.rate_a, result.rate_b, min(result.n_a, result.n_b))
    need_n = ab_test.required_sample_size(result.rate_a, C.AB_TRUE_LIFT)
    ab_row = {**result.as_dict(), "chi2": chi["chi2"], "chi2_p_value": chi["p_value"],
              "observed_power": round(power, 4), "required_n_per_group": need_n,
              "conclusion": ab_test.conclude(result)}
    pd.DataFrame([ab_row]).to_csv(C.OUTPUT_DIR / "ab_test_result.csv", index=False)

    # 6) Load into SQLite ------------------------------------------------------------
    print("[6/8] loading tables into database ...")
    loaded = load_db.load_from_disk(args.db_target)

    # 7) Excel report + 8) star schema ----------------------------------------------
    print("[7/8] building Excel report ...")
    channel_kpis = _channel_rollup(crm)
    report_excel.build_workbook(
        channel_kpis, seg.profiles, result.as_dict(), C.OUTPUT_DIR / "adpulse_report.xlsx"
    )
    print("[8/8] building Power BI star schema ...")
    star = star_schema.build_star_schema(cam)
    star_schema.save_star_schema(star)

    # --- metrics.json (every value from this run) -----------------------------------
    metrics = {
        "project": "AdPulse",
        "synthetic_data": True,
        "generated_at_utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scale": args.scale or os.getenv("ADPULSE_SCALE", "full"),
        "runtime_seconds": round((datetime.now(UTC) - t0).total_seconds(), 1),
        "generation": gen_counts,
        "pipeline": pipe,
        "channels": channel_kpis.to_dict(orient="records"),
        "anomalies": {
            "flagged_campaign_days": int(len(anomalies)),
            "by_metric": anomalies["metric"].value_counts().to_dict() if len(anomalies) else {},
        },
        "segmentation": {
            "customers": int(len(seg.rfm)),
            "chosen_k": seg.chosen_k,
            "silhouette": round(seg.silhouette, 4),
            "segments": seg.profiles.assign(
                recency=seg.profiles["recency"].round(1),
                frequency=seg.profiles["frequency"].round(2),
                monetary=seg.profiles["monetary"].round(2),
            ).to_dict(orient="records"),
        },
        "ab_test": {
            "campaign": C.AB_CAMPAIGN,
            "true_lift_injected": C.AB_TRUE_LIFT,
            "rate_control": round(result.rate_a, 5),
            "rate_variant": round(result.rate_b, 5),
            "relative_lift": round(result.rel_lift, 4),
            "z_stat": round(result.z_stat, 3),
            "p_value": round(result.p_value, 5),
            "ci95_abs_lift": [round(result.ci_low, 5), round(result.ci_high, 5)],
            "chi2": round(chi["chi2"], 3),
            "chi2_p_value": round(chi["p_value"], 5),
            "significant": result.significant,
            "observed_power": round(power, 4),
            "required_n_per_group_for_mde": need_n,
        },
        "db_tables_loaded": loaded,
    }
    with open(args.metrics_out, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print(f"\nDone in {metrics['runtime_seconds']}s. Wrote {args.metrics_out}")
    print(ab_test.conclude(result))


if __name__ == "__main__":
    main()
