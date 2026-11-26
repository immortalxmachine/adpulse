# AdPulse — Product Backlog (Jira-style)

Real-data portfolio project (Online Retail II + Marketing A/B Testing, both from Kaggle).
Story points use a Fibonacci scale (1, 2, 3, 5, 8).
Status: ✅ done · ◻️ not started. I mirror this board in a free Jira project.

---

## EPIC 1 — Real-data ingestion
Goal: stage real public data honestly (no fabricated rows) so downstream stages have real work.

- ✅ **AP-1** (3) As an analyst, I want 2 years of real transaction data so KPIs are seasonal.
  - AC: Online Retail II (UCI), ~1M rows; Invoice/StockCode/Quantity/InvoiceDate/Price/Customer ID/Country; staged from Kaggle.
- ✅ **AP-2** (2) As a data engineer, I want the pipeline to cope with the data's REAL dirt so cleaning is meaningful.
  - AC: cancellations (invoice "C…"), non-positive qty/price, missing Customer ID detected — none injected.
- ✅ **AP-3** (2) As an analyst, I want per-customer purchase history so I can build RFM.
  - AC: identified customers derived from real invoices; guest sales kept for revenue only.
- ✅ **AP-4** (3) As an analyst, I want a real A/B experiment so I can validate my stats on genuine data.
  - AC: Marketing A/B Testing dataset; ad (treatment) vs psa (control); converted flag; lift discovered, not injected.

## EPIC 2 — PySpark cleaning & KPI pipeline
Goal: a scalable, auditable transform from raw CSV to curated KPI tables.

- ✅ **AP-5** (3) As a data engineer, I want schema validation on ingest so bad files fail fast.
  - AC: fixed schema; missing column raises.
- ✅ **AP-6** (5) As a data engineer, I want bad rows quarantined with a reason so nothing is silently dropped.
  - AC: reason column; quarantine written separately; counts reported.
- ✅ **AP-7** (2) As a data engineer, I want verbatim duplicates removed so metrics aren't double-counted.
- ✅ **AP-8** (3) As a data engineer, I want cleaned data as Parquet partitioned by month so reads are cheap.
- ✅ **AP-9** (5) As an analyst, I want revenue/orders/units/AOV by country/month via Spark SQL + window functions (MoM change, country rank).

## EPIC 3 — SQL & warehouse
- ✅ **AP-10** (2) As an analyst, I want KPI tables in a database so I can query with SQL. (SQLite default; Postgres optional.)
- ✅ **AP-11** (3) As an analyst, I want 6–8 business-question SQL queries using CTEs and window functions.

## EPIC 4 — Analytics
- ✅ **AP-12** (3) As an on-call analyst, I want anomalous country-days flagged (rolling 3σ) so I catch revenue spikes.
- ✅ **AP-13** (5) As a marketer, I want customers segmented (RFM + K-Means) with k chosen by elbow + silhouette, profiled in plain English, and compared to an RFM-quantile baseline.
- ✅ **AP-14** (5) As an analyst, I want the A/B test analysed with a two-proportion z-test, CI, power/sample-size check, and a chi-square cross-check.

## EPIC 5 — Reporting
- ✅ **AP-15** (3) As a stakeholder, I want a formatted Excel workbook (KPI/segment/A-B sheets + a native chart).
- ✅ **AP-16** (3) As a BI developer, I want a Power BI-ready star schema + build notes.
- ✅ **AP-17** (2) As a viewer, I want a Streamlit dashboard for a quick look.

## EPIC 6 — Engineering quality
- ✅ **AP-18** (3) As a maintainer, I want pytest coverage of the data-prep, DQ rules, KPI maths, RFM and A/B stats.
- ✅ **AP-19** (2) As a maintainer, I want Ruff linting so style stays consistent.
- ✅ **AP-20** (3) As a maintainer, I want Docker + GitHub Actions CI (Java 17) running lint, tests and a pipeline smoke test on a committed real sample.

---

### Backlog / future (not built)
- ◻️ **AP-21** (5) Orchestrate with Airflow/Prefect instead of a single run script.
- ◻️ **AP-22** (3) Add great_expectations for declarative data contracts.
- ◻️ **AP-23** (5) Incremental/partitioned reprocessing instead of full refresh.
- ◻️ **AP-24** (3) Bayesian A/B testing alternative to the frequentist z-test.
