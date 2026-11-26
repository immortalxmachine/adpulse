"""Generate synthetic digital-advertising data.

Produces three raw CSVs under data/raw:
  * impressions.csv   - impression-level ad log (the big table; ~2M rows at full scale)
  * customers.csv     - customer master (~50k at full scale)
  * transactions.csv  - purchase history used to build RFM features

The impressions table is deliberately "dirty": it contains nulls, duplicates, negative
spend and malformed dates so the Spark stage has real data-quality work to do. One
campaign (``AB_CAMPAIGN``) serves two creatives 50/50 with a KNOWN conversion-rate lift
so the A/B test has a ground truth to recover.

Everything is driven by a single NumPy ``Generator`` seeded from ``config.RANDOM_SEED``,
so repeated runs are byte-for-byte identical.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

import numpy as np
import pandas as pd

from . import config as C


# --------------------------------------------------------------------------------------
# Campaign catalogue
# --------------------------------------------------------------------------------------
def build_campaigns(rng: np.random.Generator) -> pd.DataFrame:
    """Create the campaign dimension: name, channel, and per-campaign funnel multipliers.

    Each regular campaign inherits its channel's priors, nudged by a random multiplier so
    campaigns within a channel differ. The dedicated A/B campaign is appended last.
    """
    rows: list[dict] = []
    for i in range(C.N_CAMPAIGNS):
        channel = C.CHANNELS[i % len(C.CHANNELS)]
        priors = C.CHANNEL_PRIORS[channel]
        rows.append(
            {
                "campaign": f"{channel}_cmp_{i:02d}",
                "channel": channel,
                # lognormal-ish multipliers keep rates positive and modestly dispersed
                "ctr": float(priors["ctr"] * rng.uniform(0.7, 1.4)),
                "cvr": float(priors["cvr"] * rng.uniform(0.7, 1.4)),
                "aov": float(priors["aov"] * rng.uniform(0.85, 1.2)),
                "billing": priors["billing"],
                "cost": float(priors["cost"] * rng.uniform(0.85, 1.2)),
                "weight": float(rng.uniform(0.5, 1.5)),  # relative impression share
            }
        )

    # Dedicated A/B campaign (creative split handled later in build_impressions).
    priors = C.CHANNEL_PRIORS[C.AB_CHANNEL]
    rows.append(
        {
            "campaign": C.AB_CAMPAIGN,
            "channel": C.AB_CHANNEL,
            "ctr": float(priors["ctr"] * 1.1),
            "cvr": C.AB_BASE_CVR,  # control rate; test variant lift applied per-creative
            "aov": float(priors["aov"]),
            "billing": priors["billing"],
            "cost": float(priors["cost"]),
            "weight": 0.0,  # share is fixed separately via AB_SHARE_OF_IMPRESSIONS
        }
    )
    return pd.DataFrame(rows)


def _allocate_impressions(
    rng: np.random.Generator, campaigns: pd.DataFrame, n_total: int
) -> np.ndarray:
    """Return an integer array: how many impressions each campaign gets.

    The A/B campaign takes a fixed share; the rest is split across regular campaigns in
    proportion to their ``weight``.
    """
    counts = np.zeros(len(campaigns), dtype=np.int64)
    ab_idx = campaigns.index[campaigns["campaign"] == C.AB_CAMPAIGN][0]
    n_ab = int(round(n_total * C.AB_SHARE_OF_IMPRESSIONS))
    counts[ab_idx] = n_ab

    regular = campaigns[campaigns["campaign"] != C.AB_CAMPAIGN]
    weights = regular["weight"].to_numpy()
    weights = weights / weights.sum()
    n_regular = n_total - n_ab
    alloc = (weights * n_regular).astype(np.int64)
    alloc[-1] += n_regular - alloc.sum()  # fix rounding drift on the last campaign
    counts[regular.index.to_numpy()] = alloc
    return counts


def _random_dates(rng: np.random.Generator, n: int) -> np.ndarray:
    """Draw n dates in [START_DATE, END_DATE] with a mild weekend dip and a Dec spike."""
    span_days = (C.END_DATE - C.START_DATE).days
    day_offsets = np.arange(span_days + 1)
    dates = [C.START_DATE + timedelta(days=int(d)) for d in day_offsets]
    # Seasonality weights: weekends slightly lower, December ~40% higher (holiday push).
    weights = np.ones(len(dates))
    for j, d in enumerate(dates):
        if d.weekday() >= 5:
            weights[j] *= 0.8
        if d.month == 12:
            weights[j] *= 1.4
    weights = weights / weights.sum()
    picks = rng.choice(day_offsets, size=n, p=weights)
    base = np.datetime64(C.START_DATE)
    return base + picks.astype("timedelta64[D]")


def build_impressions(rng: np.random.Generator, campaigns: pd.DataFrame, n_total: int) -> pd.DataFrame:
    """Simulate the impression-level ad log (clean, before dirt injection).

    Funnel per impression: click ~ Bernoulli(ctr); conversion ~ Bernoulli(cvr) only if
    clicked. Spend is a CPM cost per impression; revenue is AOV per conversion. The A/B
    campaign splits creatives 50/50 and applies ``AB_TRUE_LIFT`` to creative_B's cvr.
    """
    alloc = _allocate_impressions(rng, campaigns, n_total)
    frames: list[pd.DataFrame] = []

    for idx, camp in campaigns.iterrows():
        n = int(alloc[idx])
        if n == 0:
            continue

        is_ab = camp["campaign"] == C.AB_CAMPAIGN
        if is_ab:
            creative = rng.choice(C.AB_CREATIVES, size=n)
            # control rate for A, lifted rate for B
            cvr = np.where(
                creative == "creative_B",
                camp["cvr"] * (1.0 + C.AB_TRUE_LIFT),
                camp["cvr"],
            )
        else:
            creative = np.full(n, C.DEFAULT_CREATIVE)
            cvr = np.full(n, camp["cvr"])

        clicks = rng.binomial(1, camp["ctr"], size=n)
        conversions = np.where(clicks == 1, rng.binomial(1, cvr, size=n), 0)

        # Spend depends on the billing model:
        #   CPC  -> charged per click:        spend = clicks * cost_per_click
        #   CPM  -> charged per impression:   spend = cost_per_1000 / 1000
        noise = rng.lognormal(mean=0.0, sigma=0.25, size=n)
        if camp["billing"] == "cpc":
            spend = clicks * camp["cost"] * noise
        else:  # cpm
            spend = (camp["cost"] / 1000.0) * noise
        revenue = conversions * camp["aov"] * rng.lognormal(mean=0.0, sigma=0.20, size=n)

        frames.append(
            pd.DataFrame(
                {
                    "date": _random_dates(rng, n),
                    "campaign": camp["campaign"],
                    "channel": camp["channel"],
                    "creative": creative,
                    "region": rng.choice(C.REGIONS, size=n, p=C.REGION_WEIGHTS),
                    "device": rng.choice(C.DEVICES, size=n, p=C.DEVICE_WEIGHTS),
                    "impressions": np.ones(n, dtype=np.int32),
                    "clicks": clicks.astype(np.int32),
                    "conversions": conversions.astype(np.int32),
                    "spend": np.round(spend, 4).astype(np.float64),
                    "revenue": np.round(revenue, 4).astype(np.float64),
                }
            )
        )

    df = pd.concat(frames, ignore_index=True)
    df = df.sample(frac=1.0, random_state=C.RANDOM_SEED).reset_index(drop=True)
    df.insert(0, "impression_id", np.arange(1, len(df) + 1, dtype=np.int64))
    return df


# --------------------------------------------------------------------------------------
# Dirty-data injection
# --------------------------------------------------------------------------------------
def inject_dirt(df: pd.DataFrame, rng: np.random.Generator, rates: C.DirtRates) -> pd.DataFrame:
    """Introduce realistic data-quality problems into a clean impressions frame.

    Returns a NEW frame (dates become strings so malformed dates can be represented).
    The kinds injected mirror the quarantine reasons in ``adpulse.data_quality``.
    """
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    n = len(out)

    # 1) Nulls in a required column (channel / region / device chosen at random).
    n_null = int(n * rates.null_rate)
    if n_null:
        rows = rng.choice(n, size=n_null, replace=False)
        cols = rng.choice(["channel", "region", "device"], size=n_null)
        for r, col in zip(rows, cols, strict=False):
            out.at[r, col] = None

    # 2) Negative spend (data-entry / refund-leak style errors).
    n_neg = int(n * rates.negative_spend_rate)
    if n_neg:
        rows = rng.choice(n, size=n_neg, replace=False)
        out.loc[rows, "spend"] = -out.loc[rows, "spend"].abs()

    # 3) Malformed / impossible dates.
    n_bad = int(n * rates.bad_date_rate)
    if n_bad:
        rows = rng.choice(n, size=n_bad, replace=False)
        bad_values = rng.choice(["", "not_a_date", "2026-13-40", "31/02/2026"], size=n_bad)
        out.loc[rows, "date"] = bad_values

    # 4) Exact duplicate rows (same impression_id) appended at the end.
    n_dup = int(n * rates.duplicate_rate)
    if n_dup:
        rows = rng.choice(n, size=n_dup, replace=False)
        out = pd.concat([out, out.iloc[rows]], ignore_index=True)

    return out


# --------------------------------------------------------------------------------------
# Customers & transactions (for RFM / segmentation)
# --------------------------------------------------------------------------------------
def build_customers(rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Customer master: id, signup date, region, acquisition channel, latent archetype.

    The archetype is ground truth drawn from ``CUSTOMER_ARCHETYPES``; it is written out but
    never used by the clustering, which must rediscover the structure from RFM alone.
    """
    signup_span = (C.AS_OF_DATE - C.START_DATE).days + 540  # allow signups before window
    offsets = rng.integers(0, signup_span, size=n)
    base = np.datetime64(C.START_DATE) - np.timedelta64(540, "D")
    signup = base + offsets.astype("timedelta64[D]")

    names = list(C.CUSTOMER_ARCHETYPES)
    shares = np.array([C.CUSTOMER_ARCHETYPES[a]["share"] for a in names])
    shares = shares / shares.sum()
    archetype = rng.choice(names, size=n, p=shares)

    return pd.DataFrame(
        {
            "customer_id": np.arange(1, n + 1, dtype=np.int64),
            "signup_date": pd.to_datetime(signup).strftime("%Y-%m-%d"),
            "region": rng.choice(C.REGIONS, size=n, p=C.REGION_WEIGHTS),
            "acq_channel": rng.choice(C.CHANNELS, size=n),
            "archetype": archetype,
        }
    )


def build_transactions(rng: np.random.Generator, customers: pd.DataFrame) -> pd.DataFrame:
    """Purchase history: one row per order, driven by each customer's latent archetype.

    Order count ~ Poisson(archetype lambda); dormant archetypes stop ordering earlier in
    their lifetime (lower ``recency_frac``) so their Recency is high. Order value is a
    lognormal around the acquisition channel's AOV, scaled by the archetype's value_mult.
    Customers with zero orders are kept implicitly (left-joined as zeros in RFM).
    """
    n = len(customers)
    arche = customers["archetype"].to_numpy()
    lam = np.array([C.CUSTOMER_ARCHETYPES[a]["orders_lambda"] for a in arche])
    rfrac = np.array([C.CUSTOMER_ARCHETYPES[a]["recency_frac"] for a in arche])
    vmult = np.array([C.CUSTOMER_ARCHETYPES[a]["value_mult"] for a in arche])
    aov = np.array([C.CHANNEL_PRIORS[c]["aov"] for c in customers["acq_channel"].to_numpy()])

    n_orders = rng.poisson(lam)
    signup = pd.to_datetime(customers["signup_date"]).to_numpy()
    as_of = np.datetime64(C.AS_OF_DATE)

    rep = np.repeat(np.arange(n), n_orders)  # customer row index, one entry per order
    total = int(rep.size)
    rep_signup = signup[rep]
    window = np.clip((as_of - rep_signup) / np.timedelta64(1, "D"), 1, None)
    # order falls within [signup, signup + recency_frac * window]
    offsets = (rng.random(total) * window * rfrac[rep]).astype("timedelta64[D]")
    order_date = rep_signup + offsets
    order_value = np.round(aov[rep] * vmult[rep] * rng.lognormal(mean=0.0, sigma=0.5, size=total), 2)

    txns = pd.DataFrame(
        {
            "customer_id": customers["customer_id"].to_numpy()[rep],
            "order_date": pd.to_datetime(order_date).strftime("%Y-%m-%d"),
            "order_value": order_value,
        }
    )
    return txns.sample(frac=1.0, random_state=C.RANDOM_SEED).reset_index(drop=True)


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------
def generate(scale: C.Scale, seed: int = C.RANDOM_SEED) -> dict[str, int]:
    """Generate all three tables, write them to data/raw, return row counts."""
    C.ensure_dirs()
    rng = np.random.default_rng(seed)

    campaigns = build_campaigns(rng)
    impressions_clean = build_impressions(rng, campaigns, scale.impressions)
    impressions_dirty = inject_dirt(impressions_clean, rng, C.DIRT)
    customers = build_customers(rng, scale.customers)
    transactions = build_transactions(rng, customers)

    impressions_dirty.to_csv(C.RAW_IMPRESSIONS_CSV, index=False)
    customers.to_csv(C.RAW_CUSTOMERS_CSV, index=False)
    transactions.to_csv(C.RAW_TRANSACTIONS_CSV, index=False)

    return {
        "impressions_rows_raw": len(impressions_dirty),
        "impressions_rows_clean": len(impressions_clean),
        "customers_rows": len(customers),
        "transactions_rows": len(transactions),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic AdPulse data.")
    parser.add_argument("--scale", choices=["full", "ci"], default=None,
                        help="Row-count preset (default: ADPULSE_SCALE env or 'full').")
    parser.add_argument("--impressions", type=int, default=None, help="Override impression rows.")
    parser.add_argument("--customers", type=int, default=None, help="Override customer rows.")
    parser.add_argument("--seed", type=int, default=C.RANDOM_SEED)
    args = parser.parse_args()

    scale = C.resolve_scale(args.scale)
    if args.impressions is not None or args.customers is not None:
        scale = C.Scale(
            impressions=args.impressions or scale.impressions,
            customers=args.customers or scale.customers,
        )

    counts = generate(scale, seed=args.seed)
    print("Generated synthetic data (all values are fictional):")
    for k, v in counts.items():
        print(f"  {k:28s} {v:>12,}")
    print(f"  written to {C.RAW_DIR}")


if __name__ == "__main__":
    main()
