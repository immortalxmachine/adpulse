-- Business question: which channel is most efficient overall?
-- Aggregates the monthly facts back to channel level and recomputes ratio KPIs
-- (ratios are not additive, so they must be recomputed from the summed components).
WITH channel_totals AS (
    SELECT
        channel,
        SUM(impressions) AS impressions,
        SUM(clicks)      AS clicks,
        SUM(conversions) AS conversions,
        SUM(spend)       AS spend,
        SUM(revenue)     AS revenue
    FROM kpi_channel_region_month
    GROUP BY channel
)
SELECT
    channel,
    impressions,
    clicks,
    conversions,
    ROUND(spend, 2)                                   AS spend,
    ROUND(revenue, 2)                                 AS revenue,
    ROUND(1.0 * clicks / impressions, 6)              AS ctr,
    ROUND(1.0 * conversions / clicks, 6)              AS cvr,
    ROUND(spend / NULLIF(conversions, 0), 2)          AS cpa,
    ROUND(revenue / NULLIF(spend, 0), 3)              AS roas
FROM channel_totals
ORDER BY roas DESC;
