"""PySpark pipeline: ingest -> validate -> quarantine -> dedupe -> clean Parquet -> KPIs.

Runs in Spark **local mode** (no cluster needed). The data-quality rules mirror
``adpulse.data_quality`` exactly, re-expressed as Spark SQL Columns, and the KPI formulas
mirror ``adpulse.kpis``. KPIs are produced with Spark SQL aggregations and window
functions (month-over-month change via ``lag``; campaign rank within month via ``rank``).

On Windows, Spark's native Parquet write can require ``winutils.exe``/``HADOOP_HOME``.
That only affects writing the cleaned Parquet "lake"; the KPI tables everything else needs
are collected to pandas and written with pyarrow, so the pipeline still yields real
metrics even if the native write is unavailable. On Linux/CI the native write works.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window

from . import config as C
from . import data_quality as DQ

# Explicit schema: we never infer, so a malformed file fails loudly instead of silently.
RAW_SCHEMA = T.StructType(
    [
        T.StructField("impression_id", T.LongType(), True),
        T.StructField("date", T.StringType(), True),  # string so bad dates survive to QA
        T.StructField("campaign", T.StringType(), True),
        T.StructField("channel", T.StringType(), True),
        T.StructField("creative", T.StringType(), True),
        T.StructField("region", T.StringType(), True),
        T.StructField("device", T.StringType(), True),
        T.StructField("impressions", T.IntegerType(), True),
        T.StructField("clicks", T.IntegerType(), True),
        T.StructField("conversions", T.IntegerType(), True),
        T.StructField("spend", T.DoubleType(), True),
        T.StructField("revenue", T.DoubleType(), True),
    ]
)


def build_spark(app_name: str = "adpulse") -> SparkSession:
    """Create a local-mode SparkSession with temp/warehouse dirs kept off C:."""
    C.ensure_dirs()
    if platform.system() == "Windows" and not os.environ.get("HADOOP_HOME"):
        # Non-fatal: only the native Parquet write is affected (see module docstring).
        print("[spark] note: HADOOP_HOME not set on Windows; native Parquet write may be skipped.")
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.local.dir", str(C.SPARK_LOCAL_DIR))
        .config("spark.sql.warehouse.dir", str(C.WAREHOUSE_DIR))
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )


def read_raw(spark: SparkSession, path: Path = C.RAW_IMPRESSIONS_CSV) -> DataFrame:
    """Read the raw impression CSV with a fixed schema (empty fields -> null)."""
    return (
        spark.read.option("header", True)
        .option("nullValue", "")
        .option("mode", "PERMISSIVE")
        .schema(RAW_SCHEMA)
        .csv(str(path))
    )


def validate_schema(df: DataFrame) -> None:
    """Fail fast if an expected column is missing from the source."""
    missing = set(RAW_SCHEMA.names) - set(df.columns)
    if missing:
        raise ValueError(f"raw data is missing required columns: {sorted(missing)}")


def _parse_date(colname: str = "date"):
    """Tolerant strict date parse: valid 'yyyy-MM-dd' -> date, anything else -> NULL.

    ``try_to_timestamp`` keeps Spark's strict parser (so '2026-13-40' is still rejected)
    but returns NULL instead of throwing on malformed input, which is what quarantining needs.
    """
    return F.try_to_timestamp(F.col(colname), F.lit("yyyy-MM-dd")).cast("date")


def with_quarantine_reason(df: DataFrame) -> DataFrame:
    """Add a ``quarantine_reason`` column mirroring adpulse.data_quality (first failing rule)."""
    parsed = _parse_date("date")
    null_required = (
        F.col("date").isNull()
        | F.col("campaign").isNull()
        | F.col("channel").isNull()
        | F.col("region").isNull()
        | F.col("device").isNull()
    )
    reason = (
        F.when(null_required, F.lit(DQ.REASON_NULL_REQUIRED))
        .when(parsed.isNull(), F.lit(DQ.REASON_BAD_DATE))
        .when(F.col("spend") < 0, F.lit(DQ.REASON_NEGATIVE_SPEND))
        .when(F.col("clicks") > F.col("impressions"), F.lit(DQ.REASON_CLICKS_GT_IMPRESSIONS))
        .when(F.col("conversions") > F.col("clicks"), F.lit(DQ.REASON_CONV_GT_CLICKS))
        .otherwise(F.lit(""))
    )
    return df.withColumn("quarantine_reason", reason)


def clean(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Split into (clean, quarantine), dedupe clean rows, parse date, add month partition."""
    tagged = with_quarantine_reason(df)
    quarantine = tagged.filter(F.col("quarantine_reason") != "")
    clean_df = (
        tagged.filter(F.col("quarantine_reason") == "")
        .drop("quarantine_reason")
        .dropDuplicates(["impression_id"])  # verbatim duplicates share an id
        .withColumn("date", _parse_date("date"))
        .withColumn("month", F.date_format(F.col("date"), "yyyy-MM"))
    )
    return clean_df, quarantine


def write_clean_parquet(clean_df: DataFrame, path: Path = C.CLEAN_DIR) -> bool:
    """Write the cleaned lake as Parquet partitioned by month. Returns True on success.

    Wrapped so a Windows native-IO failure degrades to a warning instead of aborting the run.
    """
    try:
        if path.exists():
            shutil.rmtree(path)
        clean_df.write.mode("overwrite").partitionBy("month").parquet(str(path))
        return True
    except Exception as exc:  # noqa: BLE001 - we intentionally degrade gracefully here
        print(f"[spark] skipped native Parquet write ({type(exc).__name__}): {exc}")
        return False


# --------------------------------------------------------------------------------------
# KPI computations (Spark SQL + window functions)
# --------------------------------------------------------------------------------------
def _agg_exprs() -> list:
    """Additive aggregate expressions. Built lazily: Column objects need a live Spark context."""
    return [
        F.sum("impressions").alias("impressions"),
        F.sum("clicks").alias("clicks"),
        F.sum("conversions").alias("conversions"),
        F.round(F.sum("spend"), 2).alias("spend"),
        F.round(F.sum("revenue"), 2).alias("revenue"),
    ]


def _with_ratio_kpis(df: DataFrame) -> DataFrame:
    """Add CTR/CVR/CPC/CPA/ROAS, mirroring adpulse.kpis (NULL when denominator is 0)."""
    def ratio(num: str, den: str):
        return F.when(F.col(den) == 0, None).otherwise(F.col(num) / F.col(den))

    return (
        df.withColumn("ctr", F.round(ratio("clicks", "impressions"), 6))
        .withColumn("cvr", F.round(ratio("conversions", "clicks"), 6))
        .withColumn("cpc", F.round(ratio("spend", "clicks"), 4))
        .withColumn("cpa", F.round(ratio("spend", "conversions"), 4))
        .withColumn("roas", F.round(ratio("revenue", "spend"), 4))
    )


def kpi_by_channel_region_month(clean_df: DataFrame) -> DataFrame:
    """KPIs grouped by channel x region x month."""
    grouped = clean_df.groupBy("channel", "region", "month").agg(*_agg_exprs())
    return _with_ratio_kpis(grouped).orderBy("month", "channel", "region")


def kpi_by_campaign_month(clean_df: DataFrame) -> DataFrame:
    """Per-campaign monthly KPIs with window functions: MoM spend change and rank within month."""
    grouped = _with_ratio_kpis(clean_df.groupBy("campaign", "channel", "month").agg(*_agg_exprs()))

    by_campaign = Window.partitionBy("campaign").orderBy("month")
    within_month = Window.partitionBy("month").orderBy(F.col("spend").desc())

    return (
        grouped.withColumn("prev_month_spend", F.lag("spend").over(by_campaign))
        .withColumn(
            "spend_mom_change",
            F.when(
                F.col("prev_month_spend").isNull() | (F.col("prev_month_spend") == 0), None
            ).otherwise(
                F.round((F.col("spend") - F.col("prev_month_spend")) / F.col("prev_month_spend"), 4)
            ),
        )
        .withColumn("spend_rank_in_month", F.rank().over(within_month))
        .orderBy("month", "spend_rank_in_month")
    )


def daily_campaign(clean_df: DataFrame) -> DataFrame:
    """Daily per-campaign spend and CTR, the input to anomaly detection."""
    grouped = clean_df.groupBy("campaign", "date").agg(
        F.sum("impressions").alias("impressions"),
        F.sum("clicks").alias("clicks"),
        F.round(F.sum("spend"), 2).alias("spend"),
    )
    return grouped.withColumn(
        "ctr",
        F.when(F.col("impressions") == 0, None).otherwise(F.round(F.col("clicks") / F.col("impressions"), 6)),
    ).orderBy("campaign", "date")


def ab_test_counts(clean_df: DataFrame) -> pd.DataFrame:
    """Aggregate clicks/conversions per creative for the A/B campaign (control vs variant)."""
    rows = (
        clean_df.filter(F.col("campaign") == C.AB_CAMPAIGN)
        .groupBy("creative")
        .agg(
            F.sum("impressions").alias("impressions"),
            F.sum("clicks").alias("clicks"),
            F.sum("conversions").alias("conversions"),
        )
        .orderBy("creative")
    )
    return rows.toPandas()


def run_pipeline(raw_path: Path = C.RAW_IMPRESSIONS_CSV) -> dict:
    """Run the full Spark stage. Writes KPI tables (via pandas) and returns a summary dict."""
    C.ensure_dirs()
    spark = build_spark()
    try:
        raw = read_raw(spark, raw_path)
        validate_schema(raw)
        raw = raw.cache()
        raw_count = raw.count()

        clean_df, quarantine = clean(raw)
        clean_df = clean_df.cache()
        clean_count = clean_df.count()
        quarantine = quarantine.cache()
        quarantine_count = quarantine.count()

        parquet_written = write_clean_parquet(clean_df)

        # Quarantine breakdown by reason (collected to pandas; small).
        q_breakdown = (
            quarantine.groupBy("quarantine_reason").count().orderBy("quarantine_reason").toPandas()
        )
        q_breakdown.to_csv(C.OUTPUT_DIR / "quarantine_summary.csv", index=False)

        # KPI tables -> pandas -> pyarrow/csv (cross-platform, no winutils needed).
        crm = kpi_by_channel_region_month(clean_df).toPandas()
        cam = kpi_by_campaign_month(clean_df).toPandas()
        daily = daily_campaign(clean_df).toPandas()
        ab_counts = ab_test_counts(clean_df)

        crm.to_parquet(C.OUTPUT_DIR / "kpi_channel_region_month.parquet", index=False)
        crm.to_csv(C.OUTPUT_DIR / "kpi_channel_region_month.csv", index=False)
        cam.to_parquet(C.OUTPUT_DIR / "kpi_campaign_month.parquet", index=False)
        cam.to_csv(C.OUTPUT_DIR / "kpi_campaign_month.csv", index=False)
        daily.to_parquet(C.OUTPUT_DIR / "daily_campaign.parquet", index=False)
        daily.to_csv(C.OUTPUT_DIR / "daily_campaign.csv", index=False)
        ab_counts.to_csv(C.OUTPUT_DIR / "ab_counts.csv", index=False)

        totals = {
            "impressions": int(crm["impressions"].sum()),
            "clicks": int(crm["clicks"].sum()),
            "conversions": int(crm["conversions"].sum()),
            "spend": float(round(crm["spend"].sum(), 2)),
            "revenue": float(round(crm["revenue"].sum(), 2)),
        }
        totals["overall_ctr"] = round(totals["clicks"] / totals["impressions"], 6)
        totals["overall_roas"] = round(totals["revenue"] / totals["spend"], 4)

        return {
            "raw_rows": int(raw_count),
            "clean_rows": int(clean_count),
            "quarantined_rows": int(quarantine_count),
            "duplicate_rows_removed": int(raw_count - quarantine_count - clean_count),
            "quarantine_rate": round(quarantine_count / raw_count, 4),
            "parquet_partitioned_write": parquet_written,
            "n_campaigns": int(cam["campaign"].nunique()),
            "months": int(crm["month"].nunique()),
            "totals": totals,
        }
    finally:
        spark.stop()


if __name__ == "__main__":
    import json

    summary = run_pipeline()
    print(json.dumps(summary, indent=2))
