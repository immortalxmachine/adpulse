"""Data-quality rules for the Online Retail II transaction log.

This module is the single source of truth for WHAT counts as a bad row and WHY. It is
written in plain pandas/NumPy so it is fast to unit-test and needs no Spark. The Spark
pipeline (``adpulse.spark_pipeline``) re-expresses these exact rules as Spark SQL Columns
and reuses the reason strings defined here, so the two implementations cannot drift.

The dirt here is REAL, not injected: the raw data genuinely contains cancellation
invoices (Invoice starting with "C", i.e. returns), non-positive quantities and prices,
and missing identifiers. A clean "completed sale" is a non-cancelled line with a positive
quantity and price, a valid date, and the required identifier fields present.
"""

from __future__ import annotations

import pandas as pd

# Quarantine reason codes (written into the ``quarantine_reason`` column).
REASON_NULL_REQUIRED = "null_required_field"
REASON_BAD_DATE = "bad_date"
REASON_CANCELLED = "cancelled_invoice"
REASON_NON_POSITIVE_QTY = "non_positive_quantity"
REASON_NON_POSITIVE_PRICE = "non_positive_price"

# Columns that must be present and non-null for a row to be usable.
# (Customer ID is intentionally NOT required: guest/unidentified sales are still real
#  revenue. The segmentation stage separately filters to identified customers.)
REQUIRED_FIELDS: list[str] = ["Invoice", "StockCode", "InvoiceDate", "Quantity", "Price", "Country"]

# Evaluated top-to-bottom; the first failing rule wins, so a row gets one clear reason.
_RULE_ORDER: list[str] = [
    REASON_NULL_REQUIRED,
    REASON_BAD_DATE,
    REASON_CANCELLED,
    REASON_NON_POSITIVE_QTY,
    REASON_NON_POSITIVE_PRICE,
]


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse InvoiceDate; unparseable values become NaT (not coerced to anything else)."""
    return pd.to_datetime(series, errors="coerce")


def _is_cancellation(invoice: pd.Series) -> pd.Series:
    """Cancellation/return invoices are prefixed with the letter 'C'."""
    return invoice.astype("string").str.upper().str.startswith("C").fillna(False)


def quarantine_reason(df: pd.DataFrame) -> pd.Series:
    """Return a per-row reason string (empty string = the row is a clean completed sale).

    Vectorised: each rule is a boolean mask; the first matching rule in ``_RULE_ORDER``
    is assigned as that row's reason.
    """
    reason = pd.Series([""] * len(df), index=df.index, dtype="object")

    parsed = parse_dates(df["InvoiceDate"])
    quantity = pd.to_numeric(df.get("Quantity"), errors="coerce")
    price = pd.to_numeric(df.get("Price"), errors="coerce")

    required = df[REQUIRED_FIELDS]
    masks = {
        REASON_NULL_REQUIRED: required.isna().any(axis=1)
        | (required.astype("string").apply(lambda c: c.str.strip()).fillna("").eq("").any(axis=1)),
        REASON_BAD_DATE: parsed.isna(),
        REASON_CANCELLED: _is_cancellation(df["Invoice"]),
        REASON_NON_POSITIVE_QTY: quantity <= 0,
        REASON_NON_POSITIVE_PRICE: price <= 0,
    }

    for code in _RULE_ORDER:
        mask = masks[code].fillna(False)
        # only set where no earlier rule already claimed the row
        reason = reason.where((reason != "") | ~mask, other=code)
    return reason


def split_clean_quarantine(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reference implementation used in tests: return (clean_rows, quarantined_rows).

    Quarantined rows carry an added ``quarantine_reason`` column. Clean rows get a parsed
    ``InvoiceDate`` column (datetime64) and a derived ``revenue`` = Quantity × Price.
    """
    reason = quarantine_reason(df)
    clean = df[reason == ""].copy()
    clean["InvoiceDate"] = parse_dates(clean["InvoiceDate"])
    clean["revenue"] = clean["Quantity"] * clean["Price"]
    quarantined = df[reason != ""].copy()
    quarantined["quarantine_reason"] = reason[reason != ""]
    return clean, quarantined
