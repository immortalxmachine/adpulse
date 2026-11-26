"""Unit tests for the data-quality / quarantine rules (Online Retail II schema)."""

import pandas as pd

from adpulse import data_quality as DQ


def _row(**overrides):
    base = {
        "Invoice": "489434", "StockCode": "85048", "Description": "GLASS BALL",
        "Quantity": 12, "InvoiceDate": "2009-12-01 07:45:00", "Price": 6.95,
        "Customer ID": 13085.0, "Country": "United Kingdom",
    }
    base.update(overrides)
    return base


def _frame():
    return pd.DataFrame(
        [
            _row(),                                   # 0: clean completed sale
            _row(Country=None),                       # 1: null required field
            _row(InvoiceDate="not_a_date"),           # 2: bad date
            _row(Invoice="C489434", Quantity=-12),    # 3: cancellation (return)
            _row(Quantity=-5),                        # 4: non-positive quantity
            _row(Price=0.0),                          # 5: non-positive price
        ]
    )


def test_each_reason_detected():
    reason = DQ.quarantine_reason(_frame()).tolist()
    assert reason[0] == ""
    assert reason[1] == DQ.REASON_NULL_REQUIRED
    assert reason[2] == DQ.REASON_BAD_DATE
    assert reason[3] == DQ.REASON_CANCELLED
    assert reason[4] == DQ.REASON_NON_POSITIVE_QTY
    assert reason[5] == DQ.REASON_NON_POSITIVE_PRICE


def test_split_counts_parsed_date_and_revenue():
    clean, quarantined = DQ.split_clean_quarantine(_frame())
    assert len(clean) == 1
    assert len(quarantined) == 5
    assert "quarantine_reason" in quarantined.columns
    # the surviving clean row has a real parsed timestamp and derived revenue
    assert pd.notna(clean["InvoiceDate"].iloc[0])
    assert clean["revenue"].iloc[0] == 12 * 6.95


def test_first_failing_rule_wins():
    # Null required field is evaluated before bad date.
    df = pd.DataFrame([_row(Country=None, InvoiceDate="not_a_date")])
    assert DQ.quarantine_reason(df).iloc[0] == DQ.REASON_NULL_REQUIRED
    # A cancellation with negative quantity is reported as a cancellation (evaluated first).
    df2 = pd.DataFrame([_row(Invoice="C1", Quantity=-3)])
    assert DQ.quarantine_reason(df2).iloc[0] == DQ.REASON_CANCELLED
