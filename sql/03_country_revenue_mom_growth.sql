-- Business question: how is each country's revenue trending month over month?
-- Window LAG() computes the previous month's revenue per country to derive % growth.
SELECT
    Country,
    month,
    ROUND(revenue, 2)                                               AS revenue,
    ROUND(LAG(revenue) OVER (PARTITION BY Country ORDER BY month), 2) AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (PARTITION BY Country ORDER BY month))
        / NULLIF(LAG(revenue) OVER (PARTITION BY Country ORDER BY month), 0),
        4
    )                                                               AS mom_growth
FROM kpi_country_month
ORDER BY Country, month;
