-- Business question: within each channel, which region delivers the best ROAS?
-- Window ROW_NUMBER() picks the top region per channel after aggregating over months.
WITH channel_region AS (
    SELECT
        channel,
        region,
        SUM(spend)   AS spend,
        SUM(revenue) AS revenue
    FROM kpi_channel_region_month
    GROUP BY channel, region
),
scored AS (
    SELECT
        channel,
        region,
        ROUND(revenue / NULLIF(spend, 0), 3) AS roas,
        ROUND(spend, 2)                      AS spend,
        ROW_NUMBER() OVER (
            PARTITION BY channel ORDER BY revenue / NULLIF(spend, 0) DESC
        ) AS rn
    FROM channel_region
)
SELECT channel, region, roas, spend
FROM scored
WHERE rn = 1
ORDER BY roas DESC;
