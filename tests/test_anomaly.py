"""Unit test for the rolling z-score anomaly detector."""

import pandas as pd

from adpulse import anomaly


def test_detects_injected_spike():
    # 20 stable days of spend ~100, then one obvious 10x spike.
    dates = pd.date_range("2026-01-01", periods=21, freq="D")
    spend = [100.0] * 20 + [1000.0]
    daily = pd.DataFrame({"campaign": "c1", "date": dates, "spend": spend, "ctr": 0.02})

    flags = anomaly.detect_anomalies(daily, metrics=("spend",), window=7, sigma=3.0)
    assert len(flags) == 1
    assert flags.iloc[0]["direction"] == "spike"
    assert pd.Timestamp(flags.iloc[0]["date"]) == dates[-1]


def test_stable_series_has_no_anomalies():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    daily = pd.DataFrame({"campaign": "c1", "date": dates, "spend": 100.0, "ctr": 0.02})
    flags = anomaly.detect_anomalies(daily, metrics=("spend", "ctr"), window=7, sigma=3.0)
    assert flags.empty
