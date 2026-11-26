"""Build a Power BI-ready star schema from the country-month KPI table.

A star schema (one central fact surrounded by dimension tables) is what Power BI's model
view and DAX measures expect. We emit CSV + Parquet for:
  * dim_date      - one row per month (year, quarter, month name)
  * dim_country   - one row per country (surrogate key)
  * fact_country_month - additive measures at country x month grain

Ratio KPIs (AOV, revenue per customer, ...) are intentionally NOT stored in the fact: they
are not additive, so they belong in DAX measures (see docs/powerbi.md).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C

_QUARTER = {m: (m - 1) // 3 + 1 for m in range(1, 13)}


def build_star_schema(country_month: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {table_name: DataFrame} for the star schema."""
    cm = country_month.copy()

    # dim_date
    months = sorted(cm["month"].unique())
    dim_date = pd.DataFrame({"month": months})
    parsed = pd.to_datetime(dim_date["month"] + "-01")
    dim_date["year"] = parsed.dt.year
    dim_date["month_num"] = parsed.dt.month
    dim_date["month_name"] = parsed.dt.strftime("%b %Y")
    dim_date["quarter"] = dim_date["month_num"].map(_QUARTER)
    dim_date.insert(0, "date_key", range(1, len(dim_date) + 1))

    # dim_country
    dim_country = (
        cm[["Country"]].drop_duplicates().sort_values("Country").reset_index(drop=True)
    )
    dim_country.insert(0, "country_key", range(1, len(dim_country) + 1))

    # fact (additive measures only)
    fact = cm.merge(dim_country[["country_key", "Country"]], on="Country").merge(
        dim_date[["date_key", "month"]], on="month"
    )
    fact = fact[
        ["country_key", "date_key", "revenue", "orders", "units", "customers"]
    ].reset_index(drop=True)

    return {"dim_date": dim_date, "dim_country": dim_country, "fact_country_month": fact}


def save_star_schema(tables: dict[str, pd.DataFrame], out_dir: Path | None = None) -> Path:
    """Write every star-schema table as CSV + Parquet under data/output/star."""
    out_dir = out_dir or (C.OUTPUT_DIR / "star")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return out_dir
