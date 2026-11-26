"""Unit tests for the KPI formulas (hand-computed expectations)."""

import math

from adpulse import kpis


def test_basic_ratios():
    assert kpis.ctr(50, 1000) == 0.05
    assert kpis.cvr(10, 50) == 0.2
    assert kpis.cpc(100.0, 50) == 2.0
    assert kpis.cpa(100.0, 10) == 10.0
    assert kpis.roas(300.0, 100.0) == 3.0


def test_zero_denominator_is_nan_not_error():
    # Undefined KPIs (e.g. CPC with zero clicks) must be NaN, never a crash.
    assert math.isnan(kpis.ctr(0, 0))
    assert math.isnan(kpis.cpc(10.0, 0))
    assert math.isnan(kpis.roas(10.0, 0))


def test_all_kpis_bundle():
    out = kpis.all_kpis(impressions=1000, clicks=50, conversions=10, spend=100.0, revenue=300.0)
    assert out["ctr"] == 0.05
    assert out["cvr"] == 0.2
    assert out["roas"] == 3.0
    assert math.isclose(out["cpa"], 10.0)
