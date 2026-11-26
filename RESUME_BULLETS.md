# Résumé bullets — AdPulse

Action verb + what + how + real number, ≤25 words each. Numbers come from `metrics.json`
(latest full run). All data is **real public data** (Online Retail II + Marketing A/B Testing,
Kaggle) — no synthetic rows, no fabricated values.

- Built a **PySpark** ELT pipeline over **1.07M** real retail-transaction rows, quarantining **2.4%** genuinely dirty records and computing revenue/AOV by country/month via Spark SQL window functions.

- Validated a real marketing **A/B experiment** (ad vs PSA control) with a two-proportion z-test, confirming a **+43% conversion lift** (p<1e-12) with a chi-square cross-check and power/sample-size analysis.

- Segmented **5,878** customers via **RFM + K-Means** (k=2 by silhouette 0.44), isolating a **2,332-strong Champions** cohort (£6.5K avg LTV) versus an explainable RFM-quantile baseline.

- Delivered reporting as an **openpyxl Excel** workbook, a **Power BI** star schema and a **Streamlit** dashboard; enforced quality with pytest, Ruff, Docker and GitHub Actions CI (Java 17).
