# AdPulse — Interview Notes

Likely questions with answers, each tied to the file/function that implements it. All data
is synthetic (`src/adpulse/generate_data.py`).

### 1. Why Parquet for the cleaned data, not CSV? — `spark_pipeline.write_clean_parquet`
Parquet is columnar: analytics read a few columns out of many, so column pruning avoids
reading the rest. It is compressed (run-length/dictionary) and carries a schema and column
statistics, which enable predicate pushdown. CSV is row-oriented, untyped, and uncompressed.

### 2. Why partition the Parquet by month? — `spark_pipeline.clean` (`month` column)
Most queries filter by time. Partitioning by `month` lets Spark skip entire folders
(partition pruning) instead of scanning a year of data to answer a one-month question.
I avoid over-partitioning (e.g. by day) because tiny files hurt throughput.

### 3. Explain Spark lazy evaluation. — throughout `spark_pipeline`
Transformations (`filter`, `groupBy`, `withColumn`) only build a logical plan; nothing runs
until an **action** (`count`, `toPandas`, `write`). Spark's Catalyst optimizer then rewrites
the whole plan (predicate pushdown, column pruning) before executing. That is why I `cache()`
the cleaned DataFrame — it is used by several KPI actions and I don't want to recompute it.

### 4. Why quarantine bad rows with a reason instead of dropping them? — `data_quality.quarantine_reason`
Silently dropping data hides problems and makes totals wrong without anyone noticing.
Writing rejects to a side table with a `quarantine_reason` makes data quality observable and
auditable — you can monitor the quarantine rate and alert if it spikes.

### 5. Why "first failing rule wins" for the reason? — `data_quality._RULE_ORDER`
A row can fail several checks; one clear reason per row keeps the quarantine report simple and
the rule order documents priority (a null required field is reported before a bad date).

### 6. How do you deduplicate, and why that key? — `spark_pipeline.clean` (`dropDuplicates(["impression_id"])`)
`impression_id` is the natural key of an impression event; verbatim duplicates share it.
Deduping on the key (not all columns) is robust even if a non-key column were re-encoded.

### 7. Which window functions did you use and why? — `spark_pipeline.kpi_by_campaign_month`
`LAG(spend) OVER (PARTITION BY campaign ORDER BY month)` for month-over-month change, and
`RANK() OVER (PARTITION BY month ORDER BY spend DESC)` to rank campaigns within each month.
Window functions compute per-row context without collapsing rows like `GROUP BY` would.

### 8. Why recompute ratio KPIs from summed components instead of averaging them? — `kpis`, `run._channel_rollup`, `star_schema`
Ratios (CTR, ROAS, …) are **not additive**: the average of daily CTRs ≠ total clicks / total
impressions. I always sum the additive numerators/denominators first, then divide. In Power BI
these are DAX measures for the same reason (`docs/powerbi.md`).

### 9. `to_date` was throwing on bad input — how did you fix it? — `spark_pipeline._parse_date`
Spark 3+/4 uses a strict datetime parser that raises on malformed text. I used
`try_to_timestamp(...)`, which keeps strict parsing (so `2026-13-40` is still rejected) but
returns NULL instead of throwing, which is exactly what the quarantine step needs.

### 10. Define the KPIs. — `kpis`
CTR = clicks/impressions; CVR = conversions/clicks; CPC = spend/clicks;
CPA = spend/conversions; ROAS = revenue/spend. `safe_div` returns NaN on a zero denominator so
an undefined KPI never crashes or silently reads as 0.

### 11. How does anomaly detection work, and why a *trailing* window? — `anomaly.detect_anomalies`
Per campaign, I compute a rolling mean and std over the previous 7 days (`shift(1)` so today is
excluded from its own baseline) and flag days more than 3σ away. Trailing means each day is
judged only against its past — how you'd actually catch a spike the next morning.

### 12. Why 3σ? — `config.ANOMALY_SIGMA`
3σ is ~99.7% of a normal distribution, so ~0.3% false-positive rate on stable series — a
deliberate precision/recall trade-off. It's a config value so analysts can tune sensitivity.

### 13. Walk through the RFM features and preprocessing. — `segmentation.compute_rfm`, `_feature_matrix`
Recency = days since last order, Frequency = order count, Monetary = total spend. RFM is highly
right-skewed, so I `log1p`-transform then standardise (z-score). K-Means uses Euclidean distance,
so features must be on comparable scales or Monetary would dominate.

### 14. How did you choose k? — `segmentation.choose_k`
I evaluate k = 2..8 and report both inertia (elbow) and silhouette, then pick the k with the
best silhouette. Silhouette is O(n²), so I sample 5,000 points for the score. The elbow is
subjective; silhouette gives a defensible single number.

### 15. What are K-Means' assumptions / limitations?
It assumes roughly spherical, similarly-sized clusters and is sensitive to scale and to the
initial centroids (I use `n_init=10` and a fixed seed). It won't find non-convex shapes — for
those you'd reach for DBSCAN or Gaussian mixtures.

### 16. Why also build an RFM-quantile baseline? — `segmentation.rfm_quantile_baseline`
A simple, explainable 1–4 quantile scoring baseline lets me show K-Means adds value beyond a
transparent rule. Always compare a model to a cheap baseline before trusting it.

### 17. Explain the two-proportion z-test. — `ab_test.two_proportion_ztest`
It tests whether two conversion rates differ. Under H0 (equal rates) the pooled proportion
estimates the common rate; the z-statistic is the observed difference over its standard error.
I report a Wald confidence interval on the absolute lift — if it excludes 0, the result is
significant at α.

### 18. Why a power / sample-size check? — `ab_test.observed_power`, `required_sample_size`
Power is the probability of detecting a true effect. A non-significant result on an underpowered
test is inconclusive, not proof of "no effect". I report observed power and the sample size that
*would* be needed to detect the target lift, so we don't over-interpret a null.

### 19. Why a chi-square cross-check? — `ab_test.chi_square_test`
The chi-square test of independence on the 2×2 table answers the same question from a different
angle; on a 2×2 table χ² ≈ z², so agreement is a sanity check that I set the test up correctly.

### 20. Why model CPC vs CPM billing? — `generate_data.build_impressions`
Real channels bill differently: search/social typically charge per click (CPC), display/video
per thousand impressions (CPM). Modelling that makes spend — and therefore CPC/CPA/ROAS —
behave realistically instead of producing an impossible blended ROAS.

### 21. How is the project reproducible? — `config.RANDOM_SEED`
A single NumPy `Generator` seed drives all randomness and the "as-of" date is fixed, so every
run produces identical data and identical `metrics.json`. CI runs a small `ci` scale; the
committed metrics come from the full `full` scale run.

### 22. Why SQLite as default with Postgres optional? — `load_db`
SQLite needs zero setup and runs in CI, so the analyst SQL and tests work anywhere. The same
loader targets PostgreSQL (via `docker-compose`) for a more production-like demo — same SQL,
real server.
