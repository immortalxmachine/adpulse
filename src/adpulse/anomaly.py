"""Rolling-window anomaly detection on daily campaign metrics.

A campaign-day is flagged when a metric (spend or CTR) lands more than ``sigma`` trailing
rolling standard deviations away from its trailing rolling mean. Using a *trailing* window
(shifted by one day) means each day is judged only against its own recent past, which is
how an on-call analyst would actually spot a spike the morning after it happened.
"""

from __future__ import annotations

import pandas as pd

from . import config as C


def detect_anomalies(
    daily: pd.DataFrame,
    metrics: tuple[str, ...] = ("spend", "ctr"),
    window: int = C.ANOMALY_WINDOW,
    sigma: float = C.ANOMALY_SIGMA,
) -> pd.DataFrame:
    """Flag anomalous campaign-days.

    Parameters
    ----------
    daily : DataFrame with at least columns ['campaign', 'date', <metrics...>], one row
            per campaign per day.
    metrics : which numeric columns to monitor.
    window : rolling window length in days.
    sigma : number of standard deviations beyond which a point is anomalous.

    Returns a tidy DataFrame (one row per flagged campaign-day-metric) with the value, the
    rolling mean/std it was compared against, the z-score, and the direction.
    """
    daily = daily.sort_values(["campaign", "date"]).copy()
    out: list[pd.DataFrame] = []

    for metric in metrics:
        grp = daily.groupby("campaign")[metric]
        # shift(1) => trailing window: today is NOT included in its own baseline.
        roll = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=window).mean())
        std = grp.transform(lambda s: s.shift(1).rolling(window, min_periods=window).std())
        z = (daily[metric] - roll) / std

        flagged = daily.loc[z.abs() > sigma, ["campaign", "date", metric]].copy()
        if flagged.empty:
            continue
        flagged["metric"] = metric
        flagged = flagged.rename(columns={metric: "value"})
        flagged["rolling_mean"] = roll[flagged.index]
        flagged["rolling_std"] = std[flagged.index]
        flagged["zscore"] = z[flagged.index]
        flagged["direction"] = flagged["zscore"].apply(lambda v: "spike" if v > 0 else "drop")
        out.append(flagged)

    if not out:
        return pd.DataFrame(
            columns=["campaign", "date", "metric", "value", "rolling_mean",
                     "rolling_std", "zscore", "direction"]
        )
    result = pd.concat(out, ignore_index=True)
    return result.sort_values(["date", "campaign", "metric"]).reset_index(drop=True)
