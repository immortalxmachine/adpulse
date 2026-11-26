-- Business question: which campaigns triggered the most anomalies, and in which direction?
-- Aggregates the anomaly log produced by the rolling z-score detector.
SELECT
    campaign,
    metric,
    direction,
    COUNT(*)                     AS n_flags,
    ROUND(AVG(ABS(zscore)), 2)   AS avg_abs_z,
    MIN(date)                    AS first_flag,
    MAX(date)                    AS last_flag
FROM anomalies
GROUP BY campaign, metric, direction
ORDER BY n_flags DESC, avg_abs_z DESC;
