# Building the Power BI dashboard

The pipeline exports a Power BI-ready **star schema** to `data/output/star/` (CSV + Parquet):

| Table | Grain | Key columns |
|-------|-------|-------------|
| `fact_country_month` | one row per country per month | `country_key`, `date_key`, additive measures |
| `dim_country` | one row per country | `country_key`, `Country` |
| `dim_date` | one row per month | `date_key`, `year`, `quarter`, `month_name` |

Only **additive** measures (revenue, orders, units, customers) live in the fact. Ratio KPIs
(AOV, units per order, …) are **DAX measures** so they aggregate correctly at every level of
the hierarchy — never pre-average a ratio. Note that `customers` is the distinct count *within
a country-month*; it is semi-additive, so roll it up with `DISTINCTCOUNT` on the source rather
than `SUM` when you need an all-time distinct customer count.

## Steps
1. **Get data → Folder / Text-CSV** and load the three files from `data/output/star/`.
2. **Model view:** create relationships
   `fact_country_month[country_key] → dim_country[country_key]` and
   `fact_country_month[date_key] → dim_date[date_key]` (both single-direction, 1-to-many).
3. Mark `dim_date` as a date table if you extend it to daily grain.
4. Add the DAX measures below.
5. Build visuals: revenue by country (bar), revenue by month (line), country table with
   conditional formatting on AOV, and a country slicer.

## Core DAX measures
```DAX
Revenue   = SUM ( fact_country_month[revenue] )
Orders    = SUM ( fact_country_month[orders] )
Units     = SUM ( fact_country_month[units] )

AOV             = DIVIDE ( [Revenue], [Orders] )
Units per Order = DIVIDE ( [Units], [Orders] )
Avg Unit Price  = DIVIDE ( [Revenue], [Units] )

-- Month-over-month revenue growth (needs a marked date table / month ordering)
Revenue MoM % =
VAR Prev = CALCULATE ( [Revenue], DATEADD ( dim_date[date_key], -1, MONTH ) )
RETURN DIVIDE ( [Revenue] - Prev, Prev )
```

> All figures come from **real public data** (Online Retail II, UCI; revenue in GBP). See the
> repository README for dataset provenance and licensing.
