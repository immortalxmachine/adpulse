# Building the Power BI dashboard

The pipeline exports a Power BI-ready **star schema** to `data/output/star/` (CSV + Parquet):

| Table | Grain | Key columns |
|-------|-------|-------------|
| `fact_campaign_month` | one row per campaign per month | `campaign_key`, `date_key`, additive measures |
| `dim_campaign` | one row per campaign | `campaign_key`, `campaign`, `channel` |
| `dim_date` | one row per month | `date_key`, `year`, `quarter`, `month_name` |

Only **additive** measures (impressions, clicks, conversions, spend, revenue) live in the
fact. Ratio KPIs (CTR, ROAS, …) are **DAX measures** so they aggregate correctly at every
level of the hierarchy — never pre-average a ratio.

## Steps
1. **Get data → Folder / Text-CSV** and load the three files from `data/output/star/`.
2. **Model view:** create relationships
   `fact_campaign_month[campaign_key] → dim_campaign[campaign_key]` and
   `fact_campaign_month[date_key] → dim_date[date_key]` (both single-direction, 1-to-many).
3. Mark `dim_date` as a date table if you extend it to daily grain.
4. Add the DAX measures below.
5. Build visuals: spend by channel (bar), ROAS by month (line), campaign table with
   conditional formatting on ROAS, and a region slicer.

## Core DAX measures
```DAX
Impressions = SUM ( fact_campaign_month[impressions] )
Clicks      = SUM ( fact_campaign_month[clicks] )
Conversions = SUM ( fact_campaign_month[conversions] )
Spend       = SUM ( fact_campaign_month[spend] )
Revenue     = SUM ( fact_campaign_month[revenue] )

CTR  = DIVIDE ( [Clicks], [Impressions] )
CVR  = DIVIDE ( [Conversions], [Clicks] )
CPC  = DIVIDE ( [Spend], [Clicks] )
CPA  = DIVIDE ( [Spend], [Conversions] )
ROAS = DIVIDE ( [Revenue], [Spend] )

-- Month-over-month spend growth (needs a marked date table / month ordering)
Spend MoM % =
VAR Prev = CALCULATE ( [Spend], DATEADD ( dim_date[date_key], -1, MONTH ) )
RETURN DIVIDE ( [Spend] - Prev, Prev )
```

> All figures are **synthetic**. See the repository README for how the data is generated.
