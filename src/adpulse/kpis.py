"""Retail KPI formulas as small, pure, testable functions.

Keeping the maths here (rather than only inside Spark expressions) means the definitions
are documented in one place and can be unit-tested with hand-computed expectations. The
Spark pipeline mirrors these exact formulas in Spark SQL.

Glossary (all derived from additive components so they recompute correctly after a SUM):
  AOV                  - average order value      = revenue / orders
  units per order      - basket size              = units / orders
  revenue per customer - customer value           = revenue / customers
  avg unit price       - price realised per unit  = revenue / units
"""

from __future__ import annotations

import math


def safe_div(numerator: float, denominator: float) -> float:
    """Divide, returning NaN when the denominator is zero (undefined KPI, not an error)."""
    if denominator is None or denominator == 0:
        return math.nan
    return numerator / denominator


def aov(revenue: float, orders: float) -> float:
    """Average order value (£ per order)."""
    return safe_div(revenue, orders)


def units_per_order(units: float, orders: float) -> float:
    """Average basket size (units per order)."""
    return safe_div(units, orders)


def revenue_per_customer(revenue: float, customers: float) -> float:
    """Average revenue per identified customer (£)."""
    return safe_div(revenue, customers)


def avg_unit_price(revenue: float, units: float) -> float:
    """Average realised price per unit (£)."""
    return safe_div(revenue, units)


def all_kpis(
    revenue: float, orders: float, units: float, customers: float
) -> dict[str, float]:
    """Compute every ratio KPI from a set of additive aggregates."""
    return {
        "aov": aov(revenue, orders),
        "units_per_order": units_per_order(units, orders),
        "revenue_per_customer": revenue_per_customer(revenue, customers),
        "avg_unit_price": avg_unit_price(revenue, units),
    }
