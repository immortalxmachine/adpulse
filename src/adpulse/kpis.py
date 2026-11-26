"""Campaign KPI formulas as small, pure, testable functions.

Keeping the maths here (rather than only inside Spark expressions) means the definitions
are documented in one place and can be unit-tested with hand-computed expectations. The
Spark pipeline mirrors these exact formulas in Spark SQL.

Glossary:
  CTR  - click-through rate      = clicks / impressions
  CVR  - conversion rate         = conversions / clicks
  CPC  - cost per click          = spend / clicks
  CPA  - cost per acquisition    = spend / conversions
  ROAS - return on ad spend      = revenue / spend
"""

from __future__ import annotations

import math


def safe_div(numerator: float, denominator: float) -> float:
    """Divide, returning NaN when the denominator is zero (undefined KPI, not an error)."""
    if denominator is None or denominator == 0:
        return math.nan
    return numerator / denominator


def ctr(clicks: float, impressions: float) -> float:
    """Click-through rate in [0, 1]."""
    return safe_div(clicks, impressions)


def cvr(conversions: float, clicks: float) -> float:
    """Conversion rate (conversions per click) in [0, 1]."""
    return safe_div(conversions, clicks)


def cpc(spend: float, clicks: float) -> float:
    """Average cost per click ($)."""
    return safe_div(spend, clicks)


def cpa(spend: float, conversions: float) -> float:
    """Average cost per acquisition ($)."""
    return safe_div(spend, conversions)


def roas(revenue: float, spend: float) -> float:
    """Return on ad spend (revenue earned per $1 spent)."""
    return safe_div(revenue, spend)


def all_kpis(
    impressions: float, clicks: float, conversions: float, spend: float, revenue: float
) -> dict[str, float]:
    """Compute every KPI from a set of additive aggregates."""
    return {
        "ctr": ctr(clicks, impressions),
        "cvr": cvr(conversions, clicks),
        "cpc": cpc(spend, clicks),
        "cpa": cpa(spend, conversions),
        "roas": roas(revenue, spend),
    }
