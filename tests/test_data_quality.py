"""Unit tests for the data-quality / quarantine rules."""

import pandas as pd

from adpulse import data_quality as DQ


def _row(**overrides):
    base = {
        "date": "2026-03-15", "campaign": "search_cmp_00", "channel": "search",
        "region": "EMEA", "device": "mobile", "impressions": 1, "clicks": 1,
        "conversions": 0, "spend": 0.01, "revenue": 0.0,
    }
    base.update(overrides)
    return base


def _frame():
    return pd.DataFrame(
        [
            _row(),                                   # 0: clean
            _row(channel=None),                       # 1: null required field
            _row(date="not_a_date"),                  # 2: bad date
            _row(date="2026-13-40"),                  # 3: impossible date
            _row(spend=-0.5),                         # 4: negative spend
            _row(clicks=5, impressions=1),            # 5: clicks > impressions
        ]
    )


def test_each_reason_detected():
    reason = DQ.quarantine_reason(_frame()).tolist()
    assert reason[0] == ""
    assert reason[1] == DQ.REASON_NULL_REQUIRED
    assert reason[2] == DQ.REASON_BAD_DATE
    assert reason[3] == DQ.REASON_BAD_DATE
    assert reason[4] == DQ.REASON_NEGATIVE_SPEND
    assert reason[5] == DQ.REASON_CLICKS_GT_IMPRESSIONS


def test_split_counts_and_parsed_date():
    clean, quarantined = DQ.split_clean_quarantine(_frame())
    assert len(clean) == 1
    assert len(quarantined) == 5
    assert "quarantine_reason" in quarantined.columns
    # the surviving clean row has a real parsed timestamp
    assert pd.notna(clean["date"].iloc[0])


def test_first_failing_rule_wins():
    # A row that is both null AND has bad date should report the null rule (evaluated first).
    df = pd.DataFrame([_row(channel=None, date="not_a_date")])
    assert DQ.quarantine_reason(df).iloc[0] == DQ.REASON_NULL_REQUIRED
