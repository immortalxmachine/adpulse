# Résumé bullets — AdPulse

Action verb + what + how + real number, ≤25 words each. Numbers come from `metrics.json`
(latest full run). All data is synthetic.

- Built a **PySpark** ELT pipeline over **2M** synthetic ad-impression rows, quarantining **1.5%** dirty records and computing CTR/CPA/ROAS by channel/region/month via Spark SQL window functions.

- Validated an ad-creative **A/B test** with a two-proportion z-test, confirming a **+11.7% conversion lift** (p=0.028) with a chi-square cross-check and power/sample-size analysis.

- Segmented **50K** customers via **RFM + K-Means** (k=3, silhouette 0.45), isolating a 17K **Champions** cohort ($627 avg LTV) versus an explainable RFM-quantile baseline.

- Delivered reporting as an **openpyxl Excel** workbook, a **Power BI** star schema and a **Streamlit** dashboard; enforced quality with pytest, Ruff, Docker and GitHub Actions CI (Java 17).
