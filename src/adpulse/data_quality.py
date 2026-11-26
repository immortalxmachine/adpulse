"""Data-quality rules for the impression log.

This module is the single source of truth for WHAT counts as a bad row and WHY. It is
written in plain pandas/NumPy so it is fast to unit-test and needs no Spark. The Spark
pipeline (``adpulse.spark_pipeline``) re-expresses these exact rules as Spark SQL
Columns and reuses the reason strings defined here, so the two implementations cannot
drift in meaning.
"""

from __future__ import annotations

import pandas as pd

# Quarantine reason codes (written into the ``quarantine_reason`` column).
REASON_NULL_REQUIRED = "null_required_field"
REASON_BAD_DATE = "bad_date"
REASON_NEGATIVE_SPEND = "negative_spend"
REASON_CLICKS_GT_IMPRESSIONS = "clicks_exceed_impressions"
REASON_CONV_GT_CLICKS = "conversions_exceed_clicks"

# Columns that must be present and non-null for a row to be usable.
REQUIRED_FIELDS: list[str] = ["date", "campaign", "channel", "region", "device"]

# Evaluated top-to-bottom; the first failing rule wins, so a row gets one clear reason.
_RULE_ORDER: list[str] = [
    REASON_NULL_REQUIRED,
    REASON_BAD_DATE,
    REASON_NEGATIVE_SPEND,
    REASON_CLICKS_GT_IMPRESSIONS,
    REASON_CONV_GT_CLICKS,
]


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse a date column strictly; unparseable values become NaT (not coerced)."""
    return pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")


def quarantine_reason(df: pd.DataFrame) -> pd.Series:
    """Return a per-row reason string (empty string = the row is clean).

    Vectorised: each rule is a boolean mask; the first matching rule in ``_RULE_ORDER``
    is assigned as that row's reason.
    """
    reason = pd.Series([""] * len(df), index=df.index, dtype="object")

    parsed = parse_dates(df["date"])
    numeric_spend = pd.to_numeric(df.get("spend"), errors="coerce")
    clicks = pd.to_numeric(df.get("clicks"), errors="coerce")
    impressions = pd.to_numeric(df.get("impressions"), errors="coerce")
    conversions = pd.to_numeric(df.get("conversions"), errors="coerce")

    masks = {
        REASON_NULL_REQUIRED: df[REQUIRED_FIELDS].isna().any(axis=1)
        | (df[REQUIRED_FIELDS].astype("string").fillna("").eq("").any(axis=1)),
        REASON_BAD_DATE: parsed.isna(),
        REASON_NEGATIVE_SPEND: numeric_spend < 0,
        REASON_CLICKS_GT_IMPRESSIONS: clicks > impressions,
        REASON_CONV_GT_CLICKS: conversions > clicks,
    }

    for code in _RULE_ORDER:
        mask = masks[code].fillna(False)
        # only set where no earlier rule already claimed the row
        reason = reason.where((reason != "") | ~mask, other=code)
    return reason


def split_clean_quarantine(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reference implementation used in tests: return (clean_rows, quarantined_rows).

    Quarantined rows carry an added ``quarantine_reason`` column. Clean rows get a parsed
    ``date`` column (datetime64) ready for downstream aggregation.
    """
    reason = quarantine_reason(df)
    clean = df[reason == ""].copy()
    clean["date"] = parse_dates(clean["date"])
    quarantined = df[reason != ""].copy()
    quarantined["quarantine_reason"] = reason[reason != ""]
    return clean, quarantined
