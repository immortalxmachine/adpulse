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
    st.title("AdPulse - Campaign Analytics (synthetic data)")
    st.caption("All data shown here is synthetic and generated locally for a portfolio demo.")

    if not C.SQLITE_DB.exists():
        st.warning("No database found. Run:  python -m adpulse.run --scale full")
        return

    crm = _load("kpi_channel_region_month")
    if not crm.empty:
        by_channel = crm.groupby("channel")[["impressions", "clicks", "conversions", "spend", "revenue"]].sum()
        by_channel["ctr"] = by_channel["clicks"] / by_channel["impressions"]
        by_channel["roas"] = by_channel["revenue"] / by_channel["spend"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Impressions", f"{int(by_channel['impressions'].sum()):,}")
        c2.metric("Spend", f"${by_channel['spend'].sum():,.0f}")
        c3.metric("Revenue", f"${by_channel['revenue'].sum():,.0f}")
        c4.metric("Overall ROAS", f"{by_channel['revenue'].sum() / by_channel['spend'].sum():.2f}x")

        st.subheader("Spend by channel")
        st.bar_chart(by_channel["spend"])
        st.subheader("KPIs by channel")
        st.dataframe(by_channel.round(4), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Customer segments")
        st.dataframe(_load("segment_profiles").round(2), use_container_width=True)
    with right:
        st.subheader("Anomalies (flagged campaign-days)")
        anoms = _load("anomalies")
        st.metric("Flagged", len(anoms))
        st.dataframe(anoms, use_container_width=True, height=240)

    st.subheader("A/B test: creative_A vs creative_B")
    ab = _load("ab_test_result")
    if not ab.empty:
        row = ab.iloc[0]
        a, b, c = st.columns(3)
        a.metric("Control CVR", f"{row['rate_a']:.2%}")
        b.metric("Variant CVR", f"{row['rate_b']:.2%}", f"{row['rel_lift']:+.1%}")
        c.metric("p-value", f"{row['p_value']:.4g}", "significant" if row["significant"] else "n.s.")
        st.info(row["conclusion"])


if __name__ == "__main__":
    main()
