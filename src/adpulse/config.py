"""Central configuration: paths, dimensions, behavioural priors, and tunables.

Keeping every magic number here means each other module reads instead of hard-codes,
and an interviewer can see the whole "shape" of the simulated business in one file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths. Everything generated lives under <repo>/data so it is easy to wipe and stays
# off the C: drive on this machine. data/ is git-ignored; nothing here is committed.
# --------------------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
CLEAN_DIR: Path = DATA_DIR / "clean"            # cleaned Parquet, partitioned by month
QUARANTINE_DIR: Path = DATA_DIR / "quarantine"  # rejected rows + reason
OUTPUT_DIR: Path = DATA_DIR / "output"          # KPI tables, star schema, reports, db
WAREHOUSE_DIR: Path = DATA_DIR / "spark-warehouse"
SPARK_LOCAL_DIR: Path = DATA_DIR / "spark-tmp"  # Spark shuffle/temp (kept off C:)
ASSETS_DIR: Path = PROJECT_ROOT / "assets"      # README screenshots/figures
METRICS_PATH: Path = PROJECT_ROOT / "metrics.json"

RAW_IMPRESSIONS_CSV: Path = RAW_DIR / "impressions.csv"
RAW_CUSTOMERS_CSV: Path = RAW_DIR / "customers.csv"
RAW_TRANSACTIONS_CSV: Path = RAW_DIR / "transactions.csv"
SQLITE_DB: Path = OUTPUT_DIR / "adpulse.db"

# --------------------------------------------------------------------------------------
# Reproducibility. One seed drives the whole generator so every run is identical.
# --------------------------------------------------------------------------------------
RANDOM_SEED: int = 42

# --------------------------------------------------------------------------------------
# Calendar: 12 months of data ending on a fixed "as of" date so metrics never drift.
# --------------------------------------------------------------------------------------
AS_OF_DATE: date = date(2026, 10, 31)
START_DATE: date = date(2025, 11, 1)
END_DATE: date = date(2026, 10, 31)

# --------------------------------------------------------------------------------------
# Dimensions.
# --------------------------------------------------------------------------------------
CHANNELS: list[str] = ["search", "social", "display", "video"]
REGIONS: list[str] = ["North America", "EMEA", "APAC", "LATAM"]
DEVICES: list[str] = ["mobile", "desktop", "tablet", "ctv"]

# Relative share of impressions per device (mobile-heavy, like real digital media).
DEVICE_WEIGHTS: list[float] = [0.55, 0.28, 0.10, 0.07]
REGION_WEIGHTS: list[float] = [0.40, 0.30, 0.20, 0.10]

# Channel-level behavioural priors used to simulate the funnel and economics.
#   ctr = click-through rate, cvr = conversion rate (conversions per click),
#   aov = average order value ($).
#   billing = how the channel is charged: "cpc" (pay per click, like search/social) or
#             "cpm" (pay per 1000 impressions, like display/video).
#   cost = the CPC ($/click) or CPM ($/1000 impressions) depending on billing.
# Values are tuned so blended ROAS lands in a realistic ~1.5-4x band per channel.
CHANNEL_PRIORS: dict[str, dict] = {
    "search": {"ctr": 0.045, "cvr": 0.085, "aov": 85.0, "billing": "cpc", "cost": 1.80},
    "social": {"ctr": 0.012, "cvr": 0.030, "aov": 60.0, "billing": "cpc", "cost": 0.60},
    "display": {"ctr": 0.004, "cvr": 0.015, "aov": 55.0, "billing": "cpm", "cost": 2.00},
    "video": {"ctr": 0.009, "cvr": 0.022, "aov": 70.0, "billing": "cpm", "cost": 4.00},
}

N_CAMPAIGNS: int = 20  # regular campaigns, in addition to the dedicated A/B campaign

# --------------------------------------------------------------------------------------
# A/B test design. One campaign serves two creatives 50/50; creative_B has a known true
# lift so our statistical test has a ground truth to recover.
# --------------------------------------------------------------------------------------
# A flagship search campaign (high CTR -> enough clicks for a powered conversion test).
AB_CAMPAIGN: str = "search_q3_launch_ab"
AB_CHANNEL: str = "search"
AB_CREATIVES: list[str] = ["creative_A", "creative_B"]
AB_BASE_CVR: float = 0.090          # post-click conversion rate of creative_A (control)
AB_TRUE_LIFT: float = 0.12          # creative_B = control * (1 + 0.12)  -> +12% relative
AB_SHARE_OF_IMPRESSIONS: float = 0.15
DEFAULT_CREATIVE: str = "default"   # creative label for all non-A/B campaigns

# --------------------------------------------------------------------------------------
# Scale. Overridable by CLI flags or the ADPULSE_SCALE env var so CI stays fast.
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Scale:
    """How many rows to simulate (order counts come from customer archetypes)."""

    impressions: int
    customers: int


FULL_SCALE: Scale = Scale(impressions=2_000_000, customers=50_000)
CI_SCALE: Scale = Scale(impressions=20_000, customers=1_000)


def resolve_scale(name: str | None = None) -> Scale:
    """Return a Scale from an explicit name, else the ADPULSE_SCALE env var, else full."""
    name = (name or os.getenv("ADPULSE_SCALE", "full")).strip().lower()
    return CI_SCALE if name == "ci" else FULL_SCALE


# --------------------------------------------------------------------------------------
# Dirty-data injection rates (applied to the raw impressions CSV only). These are the
# problems the Spark data-quality stage must detect and quarantine.
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DirtRates:
    null_rate: float = 0.010        # ~1.0% of rows get a null in a required column
    duplicate_rate: float = 0.005   # ~0.5% of rows duplicated verbatim
    negative_spend_rate: float = 0.003
    bad_date_rate: float = 0.004


DIRT: DirtRates = DirtRates()

# --------------------------------------------------------------------------------------
# Anomaly detection: flag a campaign-day whose spend or CTR is more than N rolling
# standard deviations from its own trailing rolling mean.
# --------------------------------------------------------------------------------------
ANOMALY_WINDOW: int = 7
ANOMALY_SIGMA: float = 3.0

# --------------------------------------------------------------------------------------
# Segmentation: candidate k values to evaluate with the elbow method + silhouette score.
# --------------------------------------------------------------------------------------
RFM_K_MIN: int = 2
RFM_K_MAX: int = 8

# Latent customer archetypes. The generator draws each customer from this mixture; the
# clustering never sees the label and must rediscover the structure from RFM alone.
#   orders_lambda = mean #orders (Poisson)
#   recency_frac  = how far into [signup, as_of] their orders can fall (low => dormant)
#   value_mult    = multiplier on order value
CUSTOMER_ARCHETYPES: dict[str, dict] = {
    "champion": {"share": 0.12, "orders_lambda": 9.0, "recency_frac": 1.00, "value_mult": 1.4},
    "loyal": {"share": 0.23, "orders_lambda": 5.0, "recency_frac": 0.92, "value_mult": 1.1},
    "promising": {"share": 0.25, "orders_lambda": 2.5, "recency_frac": 0.80, "value_mult": 0.9},
    "at_risk": {"share": 0.22, "orders_lambda": 3.0, "recency_frac": 0.40, "value_mult": 1.0},
    "hibernating": {"share": 0.18, "orders_lambda": 1.0, "recency_frac": 0.22, "value_mult": 0.7},
}


def ensure_dirs() -> None:
    """Create every output directory. Safe to call repeatedly."""
    for d in (
        DATA_DIR,
        RAW_DIR,
        CLEAN_DIR,
        QUARANTINE_DIR,
        OUTPUT_DIR,
        WAREHOUSE_DIR,
        SPARK_LOCAL_DIR,
        ASSETS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
