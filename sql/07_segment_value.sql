-- Business question: how valuable is each K-Means segment, and how big is it?
-- Joins the per-customer segment assignments to summarise value and share of base.
WITH seg AS (
    SELECT
        s.kmeans_segment,
        p.label,
        COUNT(*)          AS customers,
        AVG(s.recency)    AS avg_recency,
        AVG(s.frequency)  AS avg_frequency,
        AVG(s.monetary)   AS avg_monetary,
        SUM(s.monetary)   AS total_monetary
    FROM customer_segments s
    JOIN segment_profiles p ON p.kmeans_segment = s.kmeans_segment
    GROUP BY s.kmeans_segment, p.label
)
SELECT
    kmeans_segment,
    label,
    customers,
    ROUND(100.0 * customers / SUM(customers) OVER (), 1) AS pct_of_base,
    ROUND(avg_recency, 1)                                AS avg_recency_days,
    ROUND(avg_frequency, 2)                              AS avg_orders,
    ROUND(avg_monetary, 2)                               AS avg_ltv,
    ROUND(100.0 * total_monetary / SUM(total_monetary) OVER (), 1) AS pct_of_revenue
FROM seg
ORDER BY avg_monetary DESC;
