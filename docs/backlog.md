# AdPulse — Product Backlog (Jira-style)

Synthetic-data portfolio project. Story points use a Fibonacci scale (1, 2, 3, 5, 8).
Status: ✅ done · ◻️ not started. I mirror this board in a free Jira project.

---

## EPIC 1 — Synthetic data foundation
Goal: realistic, reproducible, deliberately-dirty ad data so downstream stages have real work.

- ✅ **AP-1** (3) As an analyst, I want 12 months of impression-level ad data so KPIs are seasonal.
  - AC: ~2M rows; columns campaign/channel/region/device/date/impressions/clicks/conversions/spend/revenue; single seed → identical reruns.
- ✅ **AP-2** (2) As a data engineer, I want injected data-quality issues so the cleaning stage is meaningful.
  - AC: nulls, verbatim duplicates, negative spend, malformed dates present at known rates.
- ✅ **AP-3** (2) As an analyst, I want ~50k customers with purchase history so I can build RFM.
  - AC: customers + transactions tables; some customers never purchase.
- ✅ **AP-4** (3) As an analyst, I want one campaign running an A/B test with a known lift so I can validate my stats.
  - AC: two creatives split 50/50; creative_B has a configurable true lift.

## EPIC 2 — PySpark cleaning & KPI pipeline
Goal: a scalable, auditable transform from raw CSV to curated KPI tables.

- ✅ **AP-5** (3) As a data engineer, I want schema validation on ingest so bad files fail fast.
  - AC: fixed schema; missing column raises.
- ✅ **AP-6** (5) As a data engineer, I want bad rows quarantined with a reason so nothing is silently dropped.
  - AC: reason column; quarantine written separately; counts reported.
- ✅ **AP-7** (2) As a data engineer, I want duplicates removed so metrics aren't double-counted.
- ✅ **AP-8** (3) As a data engineer, I want cleaned data as Parquet partitioned by month so reads are cheap.
- ✅ **AP-9** (5) As an analyst, I want CTR/CPC/CPA/ROAS/CVR by channel/region/month via Spark SQL + window functions (MoM change, campaign rank).

## EPIC 3 — SQL & warehouse
- ✅ **AP-10** (2) As an analyst, I want KPI tables in a database so I can query with SQL. (SQLite default; Postgres optional.)
- ✅ **AP-11** (3) As an analyst, I want 6–8 business-question SQL queries using CTEs and window functions.

## EPIC 4 — Analytics
- ✅ **AP-12** (3) As an on-call analyst, I want anomalous campaign-days flagged (rolling 3σ) so I catch spend spikes.
- ✅ **AP-13** (5) As a marketer, I want customers segmented (RFM + K-Means) with k chosen by elbow + silhouette, profiled in plain English, and compared to an RFM-quantile baseline.
- ✅ **AP-14** (5) As an analyst, I want the A/B test analysed with a two-proportion z-test, CI, power/sample-size check, and a chi-square cross-check.

## EPIC 5 — Reporting
- ✅ **AP-15** (3) As a stakeholder, I want a formatted Excel workbook (KPI/segment/A-B sheets + a native chart).
- ✅ **AP-16** (3) As a BI developer, I want a Power BI-ready star schema + build notes.
- ✅ **AP-17** (2) As a viewer, I want a Streamlit dashboard for a quick look.

## EPIC 6 — Engineering quality
- ✅ **AP-18** (3) As a maintainer, I want pytest coverage of the generator, DQ rules, KPI maths and A/B stats.
- ✅ **AP-19** (2) As a maintainer, I want Ruff linting so style stays consistent.
- ✅ **AP-20** (3) As a maintainer, I want Docker + GitHub Actions CI (Java 17) running lint, tests and a pipeline smoke test.

---

### Backlog / future (not built)
- ◻️ **AP-21** (5) Orchestrate with Airflow/Prefect instead of a single run script.
- ◻️ **AP-22** (3) Add great_expectations for declarative data contracts.
- ◻️ **AP-23** (5) Incremental/partitioned reprocessing instead of full refresh.
- ◻️ **AP-24** (3) Bayesian A/B testing alternative to the frequentist z-test.
