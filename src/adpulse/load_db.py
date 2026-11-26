"""Load analytics tables into a relational database for SQL querying.

Default target is a local SQLite file (zero setup, used by CI and by the analyst SQL in
``sql/``). An optional PostgreSQL target is supported for a more production-like demo; it
reads connection details from the environment and is only touched if explicitly requested.
"""

from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from . import config as C

# Logical table name -> output file produced by the pipeline / run orchestrator.
DISK_TABLES: dict[str, str] = {
    "kpi_channel_region_month": "kpi_channel_region_month.csv",
    "kpi_campaign_month": "kpi_campaign_month.csv",
    "daily_campaign": "daily_campaign.csv",
    "anomalies": "anomalies.csv",
    "customer_segments": "customer_segments.csv",
    "segment_profiles": "segment_profiles.csv",
    "ab_test_result": "ab_test_result.csv",
}


def get_engine(target: str = "sqlite") -> Engine:
    """Return a SQLAlchemy engine for 'sqlite' (default) or 'postgres'."""
    if target == "postgres":
        user = os.getenv("PGUSER", "adpulse")
        pwd = os.getenv("PGPASSWORD", "")
        host = os.getenv("PGHOST", "localhost")
        port = os.getenv("PGPORT", "5432")
        db = os.getenv("PGDATABASE", "adpulse")
        return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")
    C.ensure_dirs()
    return create_engine(f"sqlite:///{C.SQLITE_DB}")


def load_frames(frames: dict[str, pd.DataFrame], target: str = "sqlite") -> list[str]:
    """Write each DataFrame to a table (replacing it). Returns the list of tables loaded."""
    engine = get_engine(target)
    loaded: list[str] = []
    with engine.begin() as conn:
        for name, df in frames.items():
            if df is None or df.empty:
                continue
            df.to_sql(name, conn, if_exists="replace", index=False)
            loaded.append(name)
    engine.dispose()
    return loaded


def load_from_disk(target: str = "sqlite") -> list[str]:
    """Read the pipeline's output CSVs from data/output and load those that exist."""
    frames: dict[str, pd.DataFrame] = {}
    for table, fname in DISK_TABLES.items():
        path = C.OUTPUT_DIR / fname
        if path.exists():
            frames[table] = pd.read_csv(path)
    return load_frames(frames, target=target)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Load AdPulse tables into SQLite/Postgres.")
    parser.add_argument("--target", choices=["sqlite", "postgres"], default="sqlite")
    args = parser.parse_args()
    loaded = load_from_disk(args.target)
    print(f"Loaded {len(loaded)} tables into {args.target}: {', '.join(loaded)}")


if __name__ == "__main__":
    main()
