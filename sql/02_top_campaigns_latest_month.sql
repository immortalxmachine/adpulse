-- Business question: what were the top 5 campaigns by spend in the most recent month?
-- Uses a window RANK() over the latest month only.
WITH latest AS (
    SELECT MAX(month) AS m FROM kpi_campaign_month
),
ranked AS (
    SELECT
        campaign,
        channel,
        month,
        spend,
        roas,
        RANK() OVER (PARTITION BY month ORDER BY spend DESC) AS spend_rank
    FROM kpi_campaign_month
    WHERE month = (SELECT m FROM latest)
)
SELECT campaign, channel, month, ROUND(spend, 2) AS spend, ROUND(roas, 3) AS roas, spend_rank
FROM ranked
WHERE spend_rank <= 5
ORDER BY spend_rank;
