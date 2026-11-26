"""Unit tests for the RFM feature construction."""

import pandas as pd

from adpulse import segmentation as S


def _txns():
    # customer 1: two distinct invoices, recent; customer 2: one invoice, long ago.
    return pd.DataFrame(
        {
            "customer_id": [1, 1, 1, 2],
            "invoice": ["A1", "A1", "A2", "B1"],
            "order_date": ["2011-12-01", "2011-12-01", "2011-12-05", "2010-01-10"],
            "order_value": [10.0, 5.0, 20.0, 100.0],
        }
    )


def test_rfm_frequency_counts_distinct_invoices():
    rfm = S.compute_rfm(_txns(), customers=None, as_of="2011-12-10")
    r1 = rfm.set_index("customer_id").loc[1]
    r2 = rfm.set_index("customer_id").loc[2]
    assert r1["frequency"] == 2          # two distinct invoices, not three line items
    assert r1["monetary"] == 35.0        # 10 + 5 + 20
    assert r1["recency"] == 5            # 2011-12-10 minus last order 2011-12-05
    assert r2["frequency"] == 1
    assert r2["monetary"] == 100.0
    assert r2["recency"] > r1["recency"]  # customer 2 is far more dormant


def test_rfm_attaches_country_when_provided():
    customers = pd.DataFrame({"customer_id": [1, 2], "country": ["United Kingdom", "France"]})
    rfm = S.compute_rfm(_txns(), customers=customers, as_of="2011-12-10")
    assert set(rfm["country"]) == {"United Kingdom", "France"}
