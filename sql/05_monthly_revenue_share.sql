-- Business question: what share of each month's total revenue does each country take?
-- Window SUM() OVER (PARTITION BY month) gives the per-month denominator without a self-join.
SELECT
    month,
    Country,
    ROUND(revenue, 2) AS revenue,
    ROUND(
        revenue / SUM(revenue) OVER (PARTITION BY month),
        4
    ) AS revenue_share_of_month
FROM kpi_country_month
ORDER BY month, revenue_share_of_month DESC;
