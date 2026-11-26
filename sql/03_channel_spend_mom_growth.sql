-- Business question: how is each channel's spend trending month over month?
-- Window LAG() computes the previous month's spend per channel to derive % growth.
WITH channel_month AS (
    SELECT channel, month, SUM(spend) AS spend
    FROM kpi_channel_region_month
    GROUP BY channel, month
)
SELECT
    channel,
    month,
    ROUND(spend, 2)                                             AS spend,
    ROUND(LAG(spend) OVER (PARTITION BY channel ORDER BY month), 2) AS prev_month_spend,
    ROUND(
        (spend - LAG(spend) OVER (PARTITION BY channel ORDER BY month))
        / NULLIF(LAG(spend) OVER (PARTITION BY channel ORDER BY month), 0),
        4
    )                                                           AS mom_growth
FROM channel_month
ORDER BY channel, month;
