"""Unit test for the rolling z-score anomaly detector."""

import pandas as pd

from adpulse import anomaly


def test_detects_injected_spike():
    # 20 stable days of revenue ~1000, then one obvious 10x spike.
    dates = pd.date_range("2010-01-01", periods=21, freq="D")
    revenue = [1000.0] * 20 + [10000.0]
    daily = pd.DataFrame(
        {"Country": "United Kingdom", "date": dates, "revenue": revenue, "orders": 50}
    )

    flags = anomaly.detect_anomalies(daily, metrics=("revenue",), window=7, sigma=3.0)
    assert len(flags) == 1
    assert flags.iloc[0]["direction"] == "spike"
    assert pd.Timestamp(flags.iloc[0]["date"]) == dates[-1]


def test_stable_series_has_no_anomalies():
    dates = pd.date_range("2010-01-01", periods=30, freq="D")
    daily = pd.DataFrame(
        {"Country": "United Kingdom", "date": dates, "revenue": 1000.0, "orders": 50}
    )
    flags = anomaly.detect_anomalies(daily, metrics=("revenue", "orders"), window=7, sigma=3.0)
    assert flags.empty
