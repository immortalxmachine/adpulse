"""Central configuration: paths, dataset provenance, and analytics tunables.

AdPulse runs on two REAL public datasets (no synthetic rows, no fabricated values):

  1. Online Retail II (UCI) — Kaggle ``mashlyn/online-retail-ii-uci`` — a UK online
     gift retailer's real transactions, 2009-12-01 → 2011-12-09. Drives the Spark ELT,
     data-quality/quarantine, country×month revenue KPIs, anomaly detection and the
     RFM + K-Means customer segmentation. Currency is GBP (£).
  2. Marketing A/B Testing — Kaggle ``faviovaz/marketing-ab-testing`` — a real marketing
     experiment (users shown ``ad`` vs a ``psa`` public-service-ad control) with a
     ``converted`` flag. Drives the two-proportion z-test A/B analysis.

Keeping every tunable here means each module reads instead of hard-codes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths. Everything generated lives under <repo>/data so it is easy to wipe and stays
# off the C: drive on this machine. data/ is git-ignored (except data/sample, a small
# committed REAL subset used by CI); nothing large is committed.
# --------------------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
SAMPLE_DIR: Path = DATA_DIR / "sample"         # small REAL subset, committed, used by CI
CLEAN_DIR: Path = DATA_DIR / "clean"            # cleaned Parquet, partitioned by month
QUARANTINE_DIR: Path = DATA_DIR / "quarantine"  # rejected rows + reason
OUTPUT_DIR: Path = DATA_DIR / "output"          # KPI tables, star schema, reports, db
WAREHOUSE_DIR: Path = DATA_DIR / "spark-warehouse"
SPARK_LOCAL_DIR: Path = DATA_DIR / "spark-tmp"  # Spark shuffle/temp (kept off C:)
ASSETS_DIR: Path = PROJECT_ROOT / "assets"      # README screenshots/figures
METRICS_PATH: Path = PROJECT_ROOT / "metrics.json"

# Full real downloads (populated by `prepare_data`, git-ignored because of their size).
RAW_RETAIL_CSV: Path = RAW_DIR / "retail" / "online_retail_II.csv"
RAW_AB_CSV: Path = RAW_DIR / "ab" / "marketing_AB.csv"
# Small committed real subsets for the CI smoke test.
SAMPLE_RETAIL_CSV: Path = SAMPLE_DIR / "retail_sample.csv"
SAMPLE_AB_CSV: Path = SAMPLE_DIR / "ab_sample.csv"

SQLITE_DB: Path = OUTPUT_DIR / "adpulse.db"

# --------------------------------------------------------------------------------------
# Dataset provenance (cited in README / metrics.json so claims are traceable).
# --------------------------------------------------------------------------------------
RETAIL_DATASET = {
    "name": "Online Retail II (UCI)",
    "kaggle_slug": "mashlyn/online-retail-ii-uci",
    "license": "CC BY 4.0",
    "currency": "GBP",
}
AB_DATASET = {
    "name": "Marketing A/B Testing",
    "kaggle_slug": "faviovaz/marketing-ab-testing",
    "license": "CC0 / public (per Kaggle page)",
}

# --------------------------------------------------------------------------------------
# Calendar. The retail data ends 2011-12-09; RFM recency is measured from the day AFTER
# the last transaction (standard RFM convention), pinned so metrics never drift.
# --------------------------------------------------------------------------------------
AS_OF_DATE: date = date(2011, 12, 10)

# --------------------------------------------------------------------------------------
# A/B test. The experiment compares the treatment group ("ad") against the control
# ("psa", a public-service ad). The lift is DISCOVERED from the data, not injected.
# --------------------------------------------------------------------------------------
AB_CONTROL_GROUP: str = "psa"
AB_VARIANT_GROUP: str = "ad"
# Reference minimum detectable effect for the sample-size calculation (relative lift).
AB_REFERENCE_MDE: float = 0.05

# --------------------------------------------------------------------------------------
# Scale. `full` uses the complete real downloads; `ci` uses the small committed real
# sample so the CI smoke test runs end-to-end without Kaggle credentials.
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Scale:
    """Which inputs a run reads."""

    name: str
    retail_csv: Path
    ab_csv: Path


FULL_SCALE: Scale = Scale(name="full", retail_csv=RAW_RETAIL_CSV, ab_csv=RAW_AB_CSV)
CI_SCALE: Scale = Scale(name="ci", retail_csv=SAMPLE_RETAIL_CSV, ab_csv=SAMPLE_AB_CSV)


def resolve_scale(name: str | None = None) -> Scale:
    """Return a Scale from an explicit name, else the ADPULSE_SCALE env var, else full."""
    name = (name or os.getenv("ADPULSE_SCALE", "full")).strip().lower()
    return CI_SCALE if name == "ci" else FULL_SCALE


# --------------------------------------------------------------------------------------
# Anomaly detection: flag a country-day whose revenue or orders lands more than N rolling
# standard deviations from its own trailing rolling mean.
# --------------------------------------------------------------------------------------
ANOMALY_WINDOW: int = 7
ANOMALY_SIGMA: float = 3.0

# --------------------------------------------------------------------------------------
# Segmentation: candidate k values to evaluate with the elbow method + silhouette score.
# RANDOM_SEED makes K-Means / silhouette sampling reproducible (it does NOT generate data).
# --------------------------------------------------------------------------------------
RANDOM_SEED: int = 42
RFM_K_MIN: int = 2
RFM_K_MAX: int = 8


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
