"""Build a Power BI-ready star schema from the campaign-month KPI table.

A star schema (one central fact surrounded by dimension tables) is what Power BI's model
view and DAX measures expect. We emit CSV + Parquet for:
  * dim_date      - one row per month (year, quarter, month name)
  * dim_campaign  - one row per campaign (surrogate key + channel)
  * fact_campaign_month - additive measures at campaign x month grain

Ratio KPIs (CTR, ROAS, ...) are intentionally NOT stored in the fact: they are not
additive, so they belong in DAX measures (see docs/powerbi.md).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C

_QUARTER = {m: (m - 1) // 3 + 1 for m in range(1, 13)}


def build_star_schema(campaign_month: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {table_name: DataFrame} for the star schema."""
    cam = campaign_month.copy()

    # dim_date
    months = sorted(cam["month"].unique())
    dim_date = pd.DataFrame({"month": months})
    parsed = pd.to_datetime(dim_date["month"] + "-01")
    dim_date["year"] = parsed.dt.year
    dim_date["month_num"] = parsed.dt.month
    dim_date["month_name"] = parsed.dt.strftime("%b %Y")
    dim_date["quarter"] = dim_date["month_num"].map(_QUARTER)
    dim_date.insert(0, "date_key", range(1, len(dim_date) + 1))

    # dim_campaign
    dim_campaign = (
        cam[["campaign", "channel"]].drop_duplicates().sort_values("campaign").reset_index(drop=True)
    )
    dim_campaign.insert(0, "campaign_key", range(1, len(dim_campaign) + 1))

    # fact (additive measures only)
    fact = cam.merge(dim_campaign[["campaign_key", "campaign"]], on="campaign").merge(
        dim_date[["date_key", "month"]], on="month"
    )
    fact = fact[
        ["campaign_key", "date_key", "impressions", "clicks", "conversions", "spend", "revenue"]
    ].reset_index(drop=True)

    return {"dim_date": dim_date, "dim_campaign": dim_campaign, "fact_campaign_month": fact}


def save_star_schema(tables: dict[str, pd.DataFrame], out_dir: Path | None = None) -> Path:
    """Write every star-schema table as CSV + Parquet under data/output/star."""
    out_dir = out_dir or (C.OUTPUT_DIR / "star")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return out_dir
