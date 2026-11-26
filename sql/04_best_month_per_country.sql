-- Business question: within each country, which single month was its best by revenue?
-- Window ROW_NUMBER() picks the top month per country.
WITH scored AS (
    SELECT
        Country,
        month,
        ROUND(revenue, 2) AS revenue,
        orders,
        ROW_NUMBER() OVER (PARTITION BY Country ORDER BY revenue DESC) AS rn
    FROM kpi_country_month
)
SELECT Country, month AS best_month, revenue, orders
FROM scored
WHERE rn = 1
ORDER BY revenue DESC
LIMIT 15;
