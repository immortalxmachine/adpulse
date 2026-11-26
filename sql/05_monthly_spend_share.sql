-- Business question: what share of each month's total spend does each channel take?
-- Window SUM() OVER (PARTITION BY month) gives the per-month denominator without a self-join.
WITH channel_month AS (
    SELECT channel, month, SUM(spend) AS spend
    FROM kpi_channel_region_month
    GROUP BY channel, month
)
SELECT
    month,
    channel,
    ROUND(spend, 2) AS spend,
    ROUND(
        spend / SUM(spend) OVER (PARTITION BY month),
        4
    ) AS spend_share_of_month
FROM channel_month
ORDER BY month, spend_share_of_month DESC;
