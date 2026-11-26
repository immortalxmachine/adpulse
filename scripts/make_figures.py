"""Generate README figures from the pipeline's output CSVs.

Run after `python -m adpulse.run`:  python scripts/make_figures.py
Writes PNGs into assets/ and a composite demo image into docs/img/. All underlying data is
REAL public data (Online Retail II + Marketing A/B Testing); nothing is fabricated.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from adpulse import config as C  # noqa: E402

BLUE, RED, GREY, GREEN = "#2563eb", "#dc2626", "#6b7280", "#059669"
DOCS_IMG = C.PROJECT_ROOT / "docs" / "img"


def _country_rollup(top: int = 10) -> pd.DataFrame:
    cm = pd.read_csv(C.OUTPUT_DIR / "kpi_country_month.csv")
    # distinct customers are not additive across months, so only additive measures are summed.
    g = cm.groupby("Country")[["revenue", "orders", "units"]].sum()
    g["aov"] = g["revenue"] / g["orders"]
    return g.sort_values("revenue", ascending=False).head(top)


def country_performance(ax=None) -> None:
    g = _country_rollup()
    own = ax is None
    if own:
        _, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(range(len(g)), g["revenue"], color=BLUE, label="Revenue (£)")
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(g.index, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("Revenue (£)", color=BLUE)
    ax.tick_params(axis="y", labelcolor=BLUE)
    ax2 = ax.twinx()
    ax2.plot(range(len(g)), g["aov"], "o-", color=RED, label="AOV")
    ax2.set_ylabel("Avg order value (£)", color=RED)
    ax2.tick_params(axis="y", labelcolor=RED)
    ax.set_title("Revenue and AOV by country (top 10, real data)")
    if own:
        plt.tight_layout()
        plt.savefig(C.ASSETS_DIR / "country_performance.png", dpi=120)
        plt.close()


def monthly_trend(ax=None) -> None:
    m = pd.read_csv(C.OUTPUT_DIR / "kpi_monthly.csv").sort_values("month")
    own = ax is None
    if own:
        _, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(m["month"], m["revenue"], "o-", color=GREEN)
    ax.set_xticks(range(0, len(m), max(1, len(m) // 8)))
    ax.set_xticklabels(m["month"].iloc[:: max(1, len(m) // 8)], rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("Revenue (£)")
    ax.set_title("Monthly revenue trend (real data)")
    ax.grid(alpha=0.25)
    if own:
        plt.tight_layout()
        plt.savefig(C.ASSETS_DIR / "monthly_trend.png", dpi=120)
        plt.close()


def segment_sizes(ax=None) -> None:
    prof = pd.read_csv(C.OUTPUT_DIR / "segment_profiles.csv").sort_values("monetary")
    labels = [f"{r.label}\n(seg {int(r.kmeans_segment)})" for r in prof.itertuples()]
    own = ax is None
    if own:
        _, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(labels, prof["customers"], color=BLUE)
    ax.set_xlabel("Customers")
    ax.set_title("Customer segments by size (K-Means on RFM)")
    for i, (n, mval) in enumerate(zip(prof["customers"], prof["monetary"], strict=False)):
        ax.text(n, i, f" {int(n):,} · £{mval:,.0f} avg LTV", va="center", fontsize=8, color=GREY)
    if own:
        plt.tight_layout()
        plt.savefig(C.ASSETS_DIR / "segment_sizes.png", dpi=120)
        plt.close()


def ab_panel(ax) -> None:
    ab = pd.read_csv(C.OUTPUT_DIR / "ab_test_result.csv").iloc[0]
    groups = ["psa (control)", "ad (variant)"]
    rates = [ab["rate_a"] * 100, ab["rate_b"] * 100]
    bars = ax.bar(groups, rates, color=[GREY, BLUE])
    ax.set_ylabel("Conversion rate (%)")
    ax.set_title(
        f"A/B: ad vs psa  ({ab['rel_lift']:+.0%} lift, p={ab['p_value']:.2g})", fontsize=10
    )
    for b, r in zip(bars, rates, strict=False):
        ax.text(b.get_x() + b.get_width() / 2, r, f"{r:.2f}%", ha="center", va="bottom", fontsize=9)


def demo_composite() -> None:
    """A single 2x2 overview image for the top of the README."""
    DOCS_IMG.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    monthly_trend(axes[0, 0])
    country_performance(axes[0, 1])
    segment_sizes(axes[1, 0])
    ab_panel(axes[1, 1])
    fig.suptitle("AdPulse — marketing & revenue analytics on real public data", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(DOCS_IMG / "demo.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    C.ensure_dirs()
    country_performance()
    monthly_trend()
    segment_sizes()
    demo_composite()
    print(f"wrote figures to {C.ASSETS_DIR} and {DOCS_IMG / 'demo.png'}")
