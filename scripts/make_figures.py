"""Generate README figures from the pipeline's output CSVs.

Run after `python -m adpulse.run`:  python scripts/make_figures.py
Writes PNGs into assets/. All underlying data is synthetic.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from adpulse import config as C  # noqa: E402

BLUE, RED, GREY = "#2563eb", "#dc2626", "#6b7280"


def channel_performance() -> None:
    crm = pd.read_csv(C.OUTPUT_DIR / "kpi_channel_region_month.csv")
    g = crm.groupby("channel")[["spend", "revenue"]].sum()
    g["roas"] = g["revenue"] / g["spend"]
    g = g.sort_values("spend", ascending=False)

    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    ax1.bar(g.index, g["spend"], color=BLUE, label="Spend ($)")
    ax1.set_ylabel("Spend ($)", color=BLUE)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax2 = ax1.twinx()
    ax2.plot(g.index, g["roas"], "o-", color=RED, label="ROAS")
    ax2.set_ylabel("ROAS (revenue / spend)", color=RED)
    ax2.tick_params(axis="y", labelcolor=RED)
    ax1.set_title("Spend and ROAS by channel (synthetic)")
    fig.tight_layout()
    fig.savefig(C.ASSETS_DIR / "channel_performance.png", dpi=120)
    plt.close(fig)


def segment_sizes() -> None:
    prof = pd.read_csv(C.OUTPUT_DIR / "segment_profiles.csv").sort_values("monetary")
    labels = [f"{r.label}\n(seg {int(r.kmeans_segment)})" for r in prof.itertuples()]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(labels, prof["customers"], color=BLUE)
    ax.set_xlabel("Customers")
    ax.set_title("Customer segments by size (K-Means on RFM, synthetic)")
    for i, (n, m) in enumerate(zip(prof["customers"], prof["monetary"], strict=False)):
        ax.text(n, i, f" {int(n):,} · ${m:,.0f} avg LTV", va="center", fontsize=8, color=GREY)
    fig.tight_layout()
    fig.savefig(C.ASSETS_DIR / "segment_sizes.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    C.ensure_dirs()
    channel_performance()
    segment_sizes()
    print(f"wrote figures to {C.ASSETS_DIR}")
