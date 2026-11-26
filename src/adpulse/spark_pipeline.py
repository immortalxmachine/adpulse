"""PySpark pipeline: ingest -> validate -> quarantine -> dedupe -> clean Parquet -> KPIs.

Runs in Spark **local mode** (no cluster needed) over the real Online Retail II
transaction log. The data-quality rules mirror ``adpulse.data_quality`` exactly, re-expressed
as Spark SQL Columns, and the KPI formulas mirror ``adpulse.kpis``. KPIs are produced with
Spark SQL aggregations and window functions (month-over-month revenue change via ``lag``;
country rank within month via ``rank``).

On Windows, Spark's native Parquet write can require ``winutils.exe``/``HADOOP_HOME``.
That only affects writing the cleaned Parquet "lake"; every table everything else needs is
collected to pandas and written with pyarrow, so the pipeline still yields real metrics even
if the native write is unavailable. On Linux/CI the native write works.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window

from . import config as C
from . import data_quality as DQ

# Explicit schema in FILE column order: we never infer, so a malformed file fails loudly.
# Dates/ids are read as strings/doubles so bad values survive to the quarantine stage.
RAW_SCHEMA = T.StructType(
    [
        T.StructField("Invoice", T.StringType(), True),
        T.StructField("StockCode", T.StringType(), True),
        T.StructField("Description", T.StringType(), True),
        T.StructField("Quantity", T.IntegerType(), True),
        T.StructField("InvoiceDate", T.StringType(), True),
        T.StructField("Price", T.DoubleType(), True),
        T.StructField("Customer ID", T.DoubleType(), True),
        T.StructField("Country", T.StringType(), True),
    ]
)

_TS_FORMAT = "yyyy-MM-dd HH:mm:ss"


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


def read_raw(spark: SparkSession, path: Path = C.RAW_RETAIL_CSV) -> DataFrame:
    """Read the raw retail CSV with a fixed schema (empty fields -> null)."""
    return (
        spark.read.option("header", True)
        .option("nullValue", "")
        .option("mode", "PERMISSIVE")
        .option("encoding", "ISO-8859-1")
        .option("quote", '"')
        .option("escape", '"')
        .schema(RAW_SCHEMA)
        .csv(str(path))
    )


def validate_schema(df: DataFrame) -> None:
    """Fail fast if an expected column is missing from the source."""
    missing = set(RAW_SCHEMA.names) - set(df.columns)
    if missing:
        raise ValueError(f"raw data is missing required columns: {sorted(missing)}")


def _parse_ts(colname: str = "InvoiceDate"):
    """Tolerant strict timestamp parse: valid 'yyyy-MM-dd HH:mm:ss' -> ts, else NULL."""
    return F.try_to_timestamp(F.col(colname), F.lit(_TS_FORMAT))


def with_quarantine_reason(df: DataFrame) -> DataFrame:
    """Add a ``quarantine_reason`` column mirroring adpulse.data_quality (first failing rule)."""
    parsed = _parse_ts("InvoiceDate")
    null_required = (
        F.col("Invoice").isNull()
        | F.col("StockCode").isNull()
        | F.col("InvoiceDate").isNull()
        | F.col("Quantity").isNull()
        | F.col("Price").isNull()
        | F.col("Country").isNull()
    )
    is_cancel = F.upper(F.col("Invoice")).startswith("C")
    reason = (
        F.when(null_required, F.lit(DQ.REASON_NULL_REQUIRED))
        .when(parsed.isNull(), F.lit(DQ.REASON_BAD_DATE))
        .when(is_cancel, F.lit(DQ.REASON_CANCELLED))
        .when(F.col("Quantity") <= 0, F.lit(DQ.REASON_NON_POSITIVE_QTY))
        .when(F.col("Price") <= 0, F.lit(DQ.REASON_NON_POSITIVE_PRICE))
        .otherwise(F.lit(""))
    )
    return df.withColumn("quarantine_reason", reason)


def clean(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Split into (clean, quarantine); dedupe verbatim rows; parse date; add revenue+month."""
    tagged = with_quarantine_reason(df)
    quarantine = tagged.filter(F.col("quarantine_reason") != "")
    clean_df = (
        tagged.filter(F.col("quarantine_reason") == "")
        .drop("quarantine_reason")
        .dropDuplicates()  # verbatim duplicate transaction lines
        .withColumn("ts", _parse_ts("InvoiceDate"))
        .withColumn("date", F.to_date("ts"))
        .withColumn("month", F.date_format(F.col("ts"), "yyyy-MM"))
        .withColumn("revenue", F.round(F.col("Quantity") * F.col("Price"), 2))
        .withColumnRenamed("Customer ID", "customer_id")
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
        F.round(F.sum("revenue"), 2).alias("revenue"),
        F.countDistinct("Invoice").alias("orders"),
        F.sum("Quantity").alias("units"),
        F.countDistinct("customer_id").alias("customers"),
    ]


def _with_ratio_kpis(df: DataFrame) -> DataFrame:
    """Add AOV / units_per_order / revenue_per_customer, mirroring adpulse.kpis."""
    def ratio(num: str, den: str):
        return F.when(F.col(den) == 0, None).otherwise(F.col(num) / F.col(den))

    return (
        df.withColumn("aov", F.round(ratio("revenue", "orders"), 2))
        .withColumn("units_per_order", F.round(ratio("units", "orders"), 2))
        .withColumn("revenue_per_customer", F.round(ratio("revenue", "customers"), 2))
    )


def kpi_by_country_month(clean_df: DataFrame) -> DataFrame:
    """Per-country monthly KPIs with window functions: MoM revenue change and rank within month."""
    grouped = _with_ratio_kpis(clean_df.groupBy("Country", "month").agg(*_agg_exprs()))

    by_country = Window.partitionBy("Country").orderBy("month")
    within_month = Window.partitionBy("month").orderBy(F.col("revenue").desc())

    return (
        grouped.withColumn("prev_month_revenue", F.lag("revenue").over(by_country))
        .withColumn(
            "revenue_mom_change",
            F.when(
                F.col("prev_month_revenue").isNull() | (F.col("prev_month_revenue") == 0), None
            ).otherwise(
                F.round(
                    (F.col("revenue") - F.col("prev_month_revenue")) / F.col("prev_month_revenue"), 4
                )
            ),
        )
        .withColumn("revenue_rank_in_month", F.rank().over(within_month))
        .orderBy("month", "revenue_rank_in_month")
    )


def kpi_by_month(clean_df: DataFrame) -> DataFrame:
    """Company-wide monthly KPIs with MoM revenue growth (overall trend)."""
    grouped = _with_ratio_kpis(clean_df.groupBy("month").agg(*_agg_exprs()))
    by_time = Window.orderBy("month")
    return (
        grouped.withColumn("prev_month_revenue", F.lag("revenue").over(by_time))
        .withColumn(
            "revenue_mom_change",
            F.when(
                F.col("prev_month_revenue").isNull() | (F.col("prev_month_revenue") == 0), None
            ).otherwise(
                F.round(
                    (F.col("revenue") - F.col("prev_month_revenue")) / F.col("prev_month_revenue"), 4
                )
            ),
        )
        .orderBy("month")
    )


def daily_country(clean_df: DataFrame) -> DataFrame:
    """Daily per-country revenue and orders, the input to anomaly detection."""
    return (
        clean_df.groupBy("Country", "date")
        .agg(
            F.round(F.sum("revenue"), 2).alias("revenue"),
            F.countDistinct("Invoice").alias("orders"),
        )
        .orderBy("Country", "date")
    )


def customer_transactions(clean_df: DataFrame) -> DataFrame:
    """Line-level transactions for identified customers (the RFM / segmentation input)."""
    return (
        clean_df.filter(F.col("customer_id").isNotNull())
        .select(
            F.col("customer_id").cast("long").alias("customer_id"),
            F.col("Invoice").alias("invoice"),
            F.col("date").alias("order_date"),
            F.col("revenue").alias("order_value"),
            F.col("Country").alias("country"),
        )
    )


def run_pipeline(raw_path: Path = C.RAW_RETAIL_CSV) -> dict:
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
        cm = kpi_by_country_month(clean_df).toPandas()
        monthly = kpi_by_month(clean_df).toPandas()
        daily = daily_country(clean_df).toPandas()
        txns = customer_transactions(clean_df).toPandas()
        customers = (
            txns.sort_values("order_date")
            .groupby("customer_id", as_index=False)
            .agg(country=("country", "last"))
        )

        cm.to_parquet(C.OUTPUT_DIR / "kpi_country_month.parquet", index=False)
        cm.to_csv(C.OUTPUT_DIR / "kpi_country_month.csv", index=False)
        monthly.to_parquet(C.OUTPUT_DIR / "kpi_monthly.parquet", index=False)
        monthly.to_csv(C.OUTPUT_DIR / "kpi_monthly.csv", index=False)
        daily.to_parquet(C.OUTPUT_DIR / "daily_country.parquet", index=False)
        daily.to_csv(C.OUTPUT_DIR / "daily_country.csv", index=False)
        txns.drop(columns=["country"]).to_csv(
            C.OUTPUT_DIR / "customer_transactions.csv", index=False
        )
        customers.to_csv(C.OUTPUT_DIR / "customers.csv", index=False)

        totals = {
            "revenue": float(round(cm["revenue"].sum(), 2)),
            "orders": int(monthly["orders"].sum()),
            "units": int(cm["units"].sum()),
            "customers": int(customers["customer_id"].nunique()),
        }
        totals["aov"] = round(totals["revenue"] / totals["orders"], 2) if totals["orders"] else None
        totals["avg_unit_price"] = (
            round(totals["revenue"] / totals["units"], 2) if totals["units"] else None
        )

        return {
            "raw_rows": int(raw_count),
            "clean_rows": int(clean_count),
            "quarantined_rows": int(quarantine_count),
            "duplicate_rows_removed": int(raw_count - quarantine_count - clean_count),
            "quarantine_rate": round(quarantine_count / raw_count, 4),
            "parquet_partitioned_write": parquet_written,
            "n_countries": int(cm["Country"].nunique()),
            "months": int(monthly["month"].nunique()),
            "totals": totals,
        }
    finally:
        spark.stop()


if __name__ == "__main__":
    import json

    summary = run_pipeline()
    print(json.dumps(summary, indent=2))
