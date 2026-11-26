"""Stage the REAL raw datasets AdPulse runs on. No rows are generated or fabricated.

Two public Kaggle datasets back the project (see ``adpulse.config``):
  * Online Retail II (UCI)        -> data/raw/retail/online_retail_II.csv
  * Marketing A/B Testing          -> data/raw/ab/marketing_AB.csv

This module validates that the chosen scale's inputs are present and reports their row
counts. At ``full`` scale it can also download them from Kaggle on demand (requires the
``kaggle`` package and credentials); the small ``ci`` sample is committed under data/sample
so the CI smoke test runs with no credentials.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import pandas as pd

from . import config as C

_KAGGLE_TARGETS = [
    (C.RETAIL_DATASET["kaggle_slug"], C.RAW_RETAIL_CSV.parent),
    (C.AB_DATASET["kaggle_slug"], C.RAW_AB_CSV.parent),
]


def _row_count(path) -> int:
    """Fast-ish row count (reads a single column)."""
    return int(len(pd.read_csv(path, usecols=[0], encoding="latin-1")))


def try_download() -> None:
    """Best-effort Kaggle download of the FULL datasets (no-op if already present)."""
    for slug, dest in _KAGGLE_TARGETS:
        dest.mkdir(parents=True, exist_ok=True)
        print(f"[prepare] downloading {slug} -> {dest} ...")
        subprocess.run(
            [sys.executable, "-m", "kaggle", "datasets", "download", slug, "-p", str(dest), "--unzip"],
            check=True,
        )


def prepare(scale: C.Scale, download: bool = False) -> dict[str, int | str]:
    """Validate the scale's inputs exist (optionally downloading) and return row counts."""
    C.ensure_dirs()
    if download and scale.name == "full":
        try_download()

    missing = [p for p in (scale.retail_csv, scale.ab_csv) if not p.exists()]
    if missing:
        slugs = f"{C.RETAIL_DATASET['kaggle_slug']} and {C.AB_DATASET['kaggle_slug']}"
        raise FileNotFoundError(
            "Missing real input data: "
            + ", ".join(str(p) for p in missing)
            + f"\nDownload the datasets from Kaggle ({slugs}), e.g.:\n"
            f"  kaggle datasets download {C.RETAIL_DATASET['kaggle_slug']} "
            f"-p {C.RAW_RETAIL_CSV.parent} --unzip\n"
            f"  kaggle datasets download {C.AB_DATASET['kaggle_slug']} "
            f"-p {C.RAW_AB_CSV.parent} --unzip\n"
            "or re-run with --download, or use --scale ci for the committed sample."
        )

    return {
        "scale": scale.name,
        "retail_rows": _row_count(scale.retail_csv),
        "ab_rows": _row_count(scale.ab_csv),
        "retail_source": C.RETAIL_DATASET["kaggle_slug"],
        "ab_source": C.AB_DATASET["kaggle_slug"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage AdPulse's real raw data.")
    parser.add_argument("--scale", choices=["full", "ci"], default=None)
    parser.add_argument("--download", action="store_true", help="Download from Kaggle if missing.")
    args = parser.parse_args()

    scale = C.resolve_scale(args.scale)
    counts = prepare(scale, download=args.download)
    print("Staged real data (no fabricated rows):")
    for k, v in counts.items():
        print(f"  {k:16s} {v}")


if __name__ == "__main__":
    main()
