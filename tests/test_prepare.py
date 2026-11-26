"""Unit tests for the real-data staging / validation step."""

import pandas as pd
import pytest

from adpulse import config as C
from adpulse import prepare_data


def test_prepare_counts_rows(tmp_path):
    retail = tmp_path / "retail.csv"
    ab = tmp_path / "ab.csv"
    pd.DataFrame({"Invoice": ["1", "2", "3"], "Price": [1.0, 2.0, 3.0]}).to_csv(retail, index=False)
    pd.DataFrame({"test group": ["ad", "psa"], "converted": [True, False]}).to_csv(ab, index=False)

    scale = C.Scale(name="ci", retail_csv=retail, ab_csv=ab)
    counts = prepare_data.prepare(scale)
    assert counts["retail_rows"] == 3
    assert counts["ab_rows"] == 2
    assert counts["scale"] == "ci"


def test_prepare_raises_when_missing(tmp_path):
    scale = C.Scale(name="full", retail_csv=tmp_path / "nope.csv", ab_csv=tmp_path / "nope2.csv")
    with pytest.raises(FileNotFoundError):
        prepare_data.prepare(scale)
