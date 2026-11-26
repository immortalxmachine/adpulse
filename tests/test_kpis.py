"""Unit tests for the retail KPI formulas (hand-computed expectations)."""

import math

from adpulse import kpis


def test_basic_ratios():
    assert kpis.aov(1000.0, 50) == 20.0
    assert kpis.units_per_order(500, 50) == 10.0
    assert kpis.revenue_per_customer(1000.0, 25) == 40.0
    assert kpis.avg_unit_price(1000.0, 500) == 2.0


def test_zero_denominator_is_nan_not_error():
    # Undefined KPIs (e.g. AOV with zero orders) must be NaN, never a crash.
    assert math.isnan(kpis.aov(100.0, 0))
    assert math.isnan(kpis.revenue_per_customer(100.0, 0))
    assert math.isnan(kpis.avg_unit_price(100.0, 0))


def test_all_kpis_bundle():
    out = kpis.all_kpis(revenue=1000.0, orders=50, units=500, customers=25)
    assert out["aov"] == 20.0
    assert out["units_per_order"] == 10.0
    assert out["revenue_per_customer"] == 40.0
    assert math.isclose(out["avg_unit_price"], 2.0)
