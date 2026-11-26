"""End-to-end orchestrator: one command runs the whole AdPulse project on REAL data.

    python -m adpulse.run --scale full      # full real datasets, produces committed metrics.json
    python -m adpulse.run --scale ci        # committed real sample, fast smoke run (used by CI)

Steps: stage real data -> Spark pipeline -> anomaly detection -> segmentation -> A/B test ->
load SQLite -> Excel report -> Power BI star schema -> write metrics.json.

Every number written to metrics.json comes from THIS run over real public data; nothing is
hand-entered and no rows are fabricated.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import pandas as pd

from . import (
    ab_test,
    anomaly,
    load_db,
    prepare_data,
    report_excel,
    segmentation,
    spark_pipeline,
    star_schema,
)
from . import config as C


def _country_rollup(cm: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Roll country x month KPIs up to one row per country (ratios recomputed).

    Only additive measures (revenue/orders/units) are summed; distinct customer counts
    are NOT additive across months, so they are deliberately not rolled up here.
    """
    agg = cm.groupby("Country", as_index=False)[["revenue", "orders", "units"]].sum()
    agg["aov"] = (agg["revenue"] / agg["orders"].replace(0, pd.NA)).round(2)
    agg["units_per_order"] = (agg["units"] / agg["orders"].replace(0, pd.NA)).round(2)
    agg["avg_unit_price"] = (agg["revenue"] / agg["units"].replace(0, pd.NA)).round(2)
    agg["revenue"] = agg["revenue"].round(2)
    return agg.sort_values("revenue", ascending=False).reset_index(drop=True).head(top)


def _ab_counts(ab_csv) -> pd.DataFrame:
    """Aggregate the marketing A/B experiment to per-group users and conversions."""
    df = pd.read_csv(ab_csv, usecols=["test group", "converted"], encoding="latin-1")
    g = (
        df.groupby("test group")["converted"]
        .agg(users="count", conversions="sum")
        .reset_index()
        .rename(columns={"test group": "group"})
    )
    g["conversions"] = g["conversions"].astype(int)
    return g.set_index("group")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full AdPulse pipeline on real data.")
    parser.add_argument("--scale", choices=["full", "ci"], default=None)
    parser.add_argument("--download", action="store_true", help="Download inputs from Kaggle if missing.")
    parser.add_argument("--db-target", choices=["sqlite", "postgres"], default="sqlite")
    parser.add_argument("--metrics-out", default=str(C.METRICS_PATH))
    args = parser.parse_args()

    scale = C.resolve_scale(args.scale)
    C.ensure_dirs()
    t0 = datetime.now(UTC)

    # 1) Stage real data -------------------------------------------------------------
    print(f"[1/8] staging real data (scale={scale.name}) ...")
    stage = prepare_data.prepare(scale, download=args.download)

    # 2) Spark pipeline --------------------------------------------------------------
    print("[2/8] running Spark pipeline (clean + KPIs) ...")
    pipe = spark_pipeline.run_pipeline(scale.retail_csv)

    cm = pd.read_csv(C.OUTPUT_DIR / "kpi_country_month.csv")
    daily = pd.read_csv(C.OUTPUT_DIR / "daily_country.csv", parse_dates=["date"])

    # 3) Anomaly detection -----------------------------------------------------------
    print("[3/8] detecting anomalies ...")
    anomalies = anomaly.detect_anomalies(daily, metrics=("revenue", "orders"), key="Country")
    anomalies.to_csv(C.OUTPUT_DIR / "anomalies.csv", index=False)

    # 4) Segmentation ----------------------------------------------------------------
    print("[4/8] segmenting customers (RFM + K-Means) ...")
    transactions = pd.read_csv(C.OUTPUT_DIR / "customer_transactions.csv")
    customers = pd.read_csv(C.OUTPUT_DIR / "customers.csv")
    seg = segmentation.run_segmentation(transactions, customers, C.AS_OF_DATE)
    seg.rfm.to_csv(C.OUTPUT_DIR / "customer_segments.csv", index=False)
    seg.profiles.to_csv(C.OUTPUT_DIR / "segment_profiles.csv", index=False)
    seg.k_scores.to_csv(C.OUTPUT_DIR / "k_selection.csv", index=False)
    segmentation.save_k_plot(seg.k_scores, C.ASSETS_DIR / "segmentation_k.png")

    # 5) A/B test (ad vs psa control) ------------------------------------------------
    print("[5/8] running A/B test ...")
    ab_counts = _ab_counts(scale.ab_csv)
    ctrl, var = C.AB_CONTROL_GROUP, C.AB_VARIANT_GROUP
    result = ab_test.two_proportion_ztest(
        conv_a=int(ab_counts.loc[ctrl, "conversions"]), n_a=int(ab_counts.loc[ctrl, "users"]),
        conv_b=int(ab_counts.loc[var, "conversions"]), n_b=int(ab_counts.loc[var, "users"]),
    )
    chi = ab_test.chi_square_test(
        conv_a=int(ab_counts.loc[ctrl, "conversions"]), n_a=int(ab_counts.loc[ctrl, "users"]),
        conv_b=int(ab_counts.loc[var, "conversions"]), n_b=int(ab_counts.loc[var, "users"]),
    )
    power = ab_test.observed_power(result.rate_a, result.rate_b, min(result.n_a, result.n_b))
    need_n = ab_test.required_sample_size(result.rate_a, C.AB_REFERENCE_MDE)
    ab_counts.reset_index().to_csv(C.OUTPUT_DIR / "ab_counts.csv", index=False)
    ab_row = {**result.as_dict(), "chi2": chi["chi2"], "chi2_p_value": chi["p_value"],
              "observed_power": round(power, 4), "required_n_per_group": need_n,
              "conclusion": ab_test.conclude(result)}
    pd.DataFrame([ab_row]).to_csv(C.OUTPUT_DIR / "ab_test_result.csv", index=False)

    # 6) Load into SQLite ------------------------------------------------------------
    print("[6/8] loading tables into database ...")
    loaded = load_db.load_from_disk(args.db_target)

    # 7) Excel report + 8) star schema ----------------------------------------------
    print("[7/8] building Excel report ...")
    country_kpis = _country_rollup(cm)
    report_excel.build_workbook(
        country_kpis, seg.profiles, result.as_dict(), C.OUTPUT_DIR / "adpulse_report.xlsx"
    )
    print("[8/8] building Power BI star schema ...")
    star = star_schema.build_star_schema(cm)
    star_schema.save_star_schema(star)

    # --- metrics.json (every value from this run) -----------------------------------
    metrics = {
        "project": "AdPulse",
        "synthetic_data": False,
        "data_sources": {
            "retail": C.RETAIL_DATASET,
            "ab_test": C.AB_DATASET,
        },
        "generated_at_utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scale": scale.name,
        "runtime_seconds": round((datetime.now(UTC) - t0).total_seconds(), 1),
        "staging": stage,
        "currency": C.RETAIL_DATASET["currency"],
        "pipeline": pipe,
        "top_countries": country_kpis.to_dict(orient="records"),
        "anomalies": {
            "flagged_country_days": int(len(anomalies)),
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
            "control_group": ctrl,
            "variant_group": var,
            "n_control": result.n_a,
            "n_variant": result.n_b,
            "rate_control": round(result.rate_a, 5),
            "rate_variant": round(result.rate_b, 5),
            "relative_lift": round(result.rel_lift, 4),
            "z_stat": round(result.z_stat, 3),
            "p_value": result.p_value,
            "ci95_abs_lift": [round(result.ci_low, 5), round(result.ci_high, 5)],
            "chi2": round(chi["chi2"], 3),
            "chi2_p_value": chi["p_value"],
            "significant": result.significant,
            "observed_power": round(power, 4),
            "reference_mde": C.AB_REFERENCE_MDE,
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
