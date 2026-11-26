-- Business question: which countries drive the most value, and how do they buy?
-- Aggregates the monthly facts back to country level and recomputes ratio KPIs
-- (ratios are not additive, so they must be recomputed from the summed components).
WITH country_totals AS (
    SELECT
        Country,
        SUM(revenue)   AS revenue,
        SUM(orders)    AS orders,
        SUM(units)     AS units,
        SUM(customers) AS customer_months
    FROM kpi_country_month
    GROUP BY Country
)
SELECT
    Country,
    ROUND(revenue, 2)                                 AS revenue,
    orders,
    units,
    ROUND(revenue / NULLIF(orders, 0), 2)             AS aov,
    ROUND(1.0 * units / NULLIF(orders, 0), 2)         AS units_per_order,
    ROUND(revenue / NULLIF(units, 0), 2)              AS avg_unit_price
FROM country_totals
ORDER BY revenue DESC
LIMIT 15;
