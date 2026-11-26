"""Customer segmentation: RFM features + K-Means, with a transparent RFM-quantile baseline.

Pipeline:
  1. Build Recency / Frequency / Monetary features from the transaction history.
  2. Log-transform and standardise them (K-Means assumes roughly spherical, comparable
     scales; RFM is heavily right-skewed so a log helps a lot).
  3. Choose k with BOTH the elbow method (inertia) and the silhouette score, then fit.
  4. Profile each cluster in plain English.
  5. Compare against a simple, explainable RFM-quantile scoring baseline.

K-Means is unsupervised, so the "right" k is a judgement call; we report the evidence
(inertia curve + silhouette) and pick the k with the best silhouette.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from . import config as C


@dataclass
class SegmentationResult:
    rfm: pd.DataFrame                 # per-customer R/F/M + kmeans_segment + baseline_segment
    k_scores: pd.DataFrame            # per-k inertia and silhouette
    chosen_k: int
    profiles: pd.DataFrame            # per-cluster size + mean R/F/M + label
    silhouette: float


def compute_rfm(transactions: pd.DataFrame, customers: pd.DataFrame, as_of) -> pd.DataFrame:
    """Build RFM features for every customer (including those who never purchased).

    recency   = days since most recent order (capped for never-purchased at days since signup)
    frequency = number of orders
    monetary  = total spend
    """
    as_of = pd.Timestamp(as_of)
    txn = transactions.copy()
    txn["order_date"] = pd.to_datetime(txn["order_date"], errors="coerce")

    agg = txn.groupby("customer_id").agg(
        last_order=("order_date", "max"),
        frequency=("order_date", "count"),
        monetary=("order_value", "sum"),
    )

    cust = customers.copy()
    cust["signup_date"] = pd.to_datetime(cust["signup_date"], errors="coerce")
    rfm = cust.merge(agg, on="customer_id", how="left")

    rfm["frequency"] = rfm["frequency"].fillna(0).astype(int)
    rfm["monetary"] = rfm["monetary"].fillna(0.0)
    # recency: from last order if any, else from signup (treated as long-dormant)
    last = rfm["last_order"].fillna(rfm["signup_date"])
    rfm["recency"] = (as_of - last).dt.days.clip(lower=0)
    return rfm[["customer_id", "region", "acq_channel", "recency", "frequency", "monetary"]]


def _feature_matrix(rfm: pd.DataFrame) -> np.ndarray:
    """Log-transform then standardise R/F/M into a model-ready matrix."""
    feats = np.column_stack(
        [
            np.log1p(rfm["recency"].to_numpy()),
            np.log1p(rfm["frequency"].to_numpy()),
            np.log1p(rfm["monetary"].to_numpy()),
        ]
    )
    return StandardScaler().fit_transform(feats)


def choose_k(x: np.ndarray, k_min: int = C.RFM_K_MIN, k_max: int = C.RFM_K_MAX,
             seed: int = C.RANDOM_SEED) -> pd.DataFrame:
    """Evaluate candidate k values: return inertia (elbow) and silhouette for each."""
    rng_sample = min(5000, x.shape[0])  # silhouette is O(n^2); sample for speed
    rows = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = km.fit_predict(x)
        sil = silhouette_score(x, labels, sample_size=rng_sample, random_state=seed)
        rows.append({"k": k, "inertia": float(km.inertia_), "silhouette": float(sil)})
    return pd.DataFrame(rows)


def _label_segment(row: pd.Series, med: pd.Series) -> str:
    """Name a cluster from its centroid relative to the population medians."""
    recent = row["recency"] <= med["recency"]
    frequent = row["frequency"] >= med["frequency"]
    high_value = row["monetary"] >= med["monetary"]
    if row["frequency"] < 0.5:
        return "Prospects (rarely/never purchased)"
    if recent and frequent and high_value:
        return "Champions"
    if recent and (frequent or high_value):
        return "Loyal / promising"
    if not recent and (frequent or high_value):
        return "At risk (was valuable)"
    return "Hibernating / low value"


def rfm_quantile_baseline(rfm: pd.DataFrame) -> pd.Series:
    """Classic 1-4 quantile RFM scoring, used as an explainable baseline to compare K-Means.

    Recency is reversed (more recent = better = higher score).
    """
    def score(series: pd.Series, reverse: bool = False) -> pd.Series:
        ranks = series.rank(method="first")
        q = pd.qcut(ranks, 4, labels=[1, 2, 3, 4]).astype(int)
        return (5 - q) if reverse else q

    r = score(rfm["recency"], reverse=True)
    f = score(rfm["frequency"])
    m = score(rfm["monetary"])
    total = r + f + m
    bins = pd.cut(total, bins=[2, 5, 8, 10, 12], labels=["Low", "Mid", "High", "Top"],
                  include_lowest=True)
    return bins.astype("object")


def run_segmentation(transactions: pd.DataFrame, customers: pd.DataFrame, as_of) -> SegmentationResult:
    """End-to-end segmentation. Returns features, k-evidence, clusters, and profiles."""
    rfm = compute_rfm(transactions, customers, as_of)
    x = _feature_matrix(rfm)

    k_scores = choose_k(x)
    chosen_k = int(k_scores.loc[k_scores["silhouette"].idxmax(), "k"])

    km = KMeans(n_clusters=chosen_k, random_state=C.RANDOM_SEED, n_init=10)
    rfm["kmeans_segment"] = km.fit_predict(x)
    best_sil = float(k_scores.loc[k_scores["k"] == chosen_k, "silhouette"].iloc[0])

    rfm["baseline_segment"] = rfm_quantile_baseline(rfm)

    med = rfm[["recency", "frequency", "monetary"]].median()
    prof = (
        rfm.groupby("kmeans_segment")
        .agg(
            customers=("customer_id", "count"),
            recency=("recency", "mean"),
            frequency=("frequency", "mean"),
            monetary=("monetary", "mean"),
        )
        .reset_index()
    )
    prof["label"] = prof.apply(lambda r: _label_segment(r, med), axis=1)

    return SegmentationResult(
        rfm=rfm, k_scores=k_scores, chosen_k=chosen_k, profiles=prof, silhouette=best_sil
    )


def save_k_plot(k_scores: pd.DataFrame, path) -> None:
    """Save the elbow + silhouette diagnostic figure (used in the README)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    ax1.plot(k_scores["k"], k_scores["inertia"], "o-", color="#2563eb", label="Inertia (elbow)")
    ax1.set_xlabel("k (number of clusters)")
    ax1.set_ylabel("Inertia", color="#2563eb")
    ax1.tick_params(axis="y", labelcolor="#2563eb")

    ax2 = ax1.twinx()
    ax2.plot(k_scores["k"], k_scores["silhouette"], "s--", color="#dc2626", label="Silhouette")
    ax2.set_ylabel("Silhouette score", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")

    plt.title("Choosing k: elbow (inertia) vs silhouette")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
