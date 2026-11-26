-- Business question: which countries delivered the most revenue in the most recent month?
-- Uses a window RANK() over the latest month only.
WITH latest AS (
    SELECT MAX(month) AS m FROM kpi_country_month
),
ranked AS (
    SELECT
        Country,
        month,
        revenue,
        orders,
        aov,
        RANK() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank
    FROM kpi_country_month
    WHERE month = (SELECT m FROM latest)
)
SELECT Country, month, ROUND(revenue, 2) AS revenue, orders, ROUND(aov, 2) AS aov, revenue_rank
FROM ranked
WHERE revenue_rank <= 5
ORDER BY revenue_rank;
