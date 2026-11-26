"""Streamlit dashboard for quick viewing of the AdPulse results.

Run after the pipeline has populated the SQLite database:

    streamlit run src/adpulse/dashboard.py

It reads the tables written by ``adpulse.load_db`` and shows KPI summaries, the anomaly
log, customer segments, and the A/B test scorecard. Read-only: it never mutates the data.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from . import config as C


@st.cache_data
def _load(table: str) -> pd.DataFrame:
    with sqlite3.connect(C.SQLITE_DB) as conn:
        try:
            return pd.read_sql(f"SELECT * FROM {table}", conn)
        except Exception:
            return pd.DataFrame()


def main() -> None:
    st.set_page_config(page_title="AdPulse", layout="wide")
    st.title("AdPulse - Marketing & Revenue Analytics (real public data)")
    st.caption(
        "Online Retail II (UCI) + Marketing A/B Testing (Kaggle). Revenue in GBP. No PII."
    )

    if not C.SQLITE_DB.exists():
        st.warning("No database found. Run:  python -m adpulse.run --scale full")
        return

    cm = _load("kpi_country_month")
    if not cm.empty:
        by_country = cm.groupby("Country")[["revenue", "orders", "units", "customers"]].sum()
        by_country["aov"] = by_country["revenue"] / by_country["orders"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Revenue", f"£{by_country['revenue'].sum():,.0f}")
        c2.metric("Orders", f"{int(by_country['orders'].sum()):,}")
        c3.metric("Units", f"{int(by_country['units'].sum()):,}")
        c4.metric("Overall AOV", f"£{by_country['revenue'].sum() / by_country['orders'].sum():,.2f}")

        top = by_country.sort_values("revenue", ascending=False).head(10)
        st.subheader("Revenue by country (top 10)")
        st.bar_chart(top["revenue"])
        st.subheader("KPIs by country (top 10 by revenue)")
        st.dataframe(top.round(2), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Customer segments")
        st.dataframe(_load("segment_profiles").round(2), use_container_width=True)
    with right:
        st.subheader("Anomalies (flagged country-days)")
        anoms = _load("anomalies")
        st.metric("Flagged", len(anoms))
        st.dataframe(anoms, use_container_width=True, height=240)

    st.subheader("A/B test: psa (control) vs ad (variant)")
    ab = _load("ab_test_result")
    if not ab.empty:
        row = ab.iloc[0]
        a, b, c = st.columns(3)
        a.metric("Control conv. rate", f"{row['rate_a']:.2%}")
        b.metric("Variant conv. rate", f"{row['rate_b']:.2%}", f"{row['rel_lift']:+.1%}")
        c.metric("p-value", f"{row['p_value']:.4g}", "significant" if row["significant"] else "n.s.")
        st.info(row["conclusion"])


if __name__ == "__main__":
    main()
