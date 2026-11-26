"""Unit tests for the synthetic data generator (pure builders, no file IO)."""

import numpy as np
import pandas as pd

from adpulse import config as C
from adpulse import generate_data as G


def _rng():
    return np.random.default_rng(C.RANDOM_SEED)


def test_campaigns_include_ab_and_channels():
    camps = G.build_campaigns(_rng())
    assert len(camps) == C.N_CAMPAIGNS + 1
    assert C.AB_CAMPAIGN in set(camps["campaign"])
    assert set(camps["channel"]).issubset(set(C.CHANNELS))


def test_impressions_shape_and_funnel_consistency():
    camps = G.build_campaigns(_rng())
    df = G.build_impressions(_rng(), camps, n_total=20_000)
    assert len(df) == 20_000
    assert df["impression_id"].is_unique
    # conversions can never exceed clicks in the clean (pre-dirt) data
    assert (df["conversions"] <= df["clicks"]).all()
    assert (df["clicks"] <= df["impressions"]).all()
    # the A/B campaign serves exactly the two creatives
    ab = df[df["campaign"] == C.AB_CAMPAIGN]
    assert set(ab["creative"]) == set(C.AB_CREATIVES)


def test_generator_is_reproducible():
    camps1 = G.build_campaigns(_rng())
    camps2 = G.build_campaigns(_rng())
    d1 = G.build_impressions(_rng(), camps1, n_total=5_000)
    d2 = G.build_impressions(_rng(), camps2, n_total=5_000)
    pd.testing.assert_frame_equal(d1, d2)


def test_dirt_injection_creates_known_problems():
    camps = G.build_campaigns(_rng())
    clean = G.build_impressions(_rng(), camps, n_total=50_000)
    dirty = G.inject_dirt(clean, _rng(), C.DIRT)
    # duplicates make the dirty frame longer than the clean one
    assert len(dirty) > len(clean)
    # negative spend and malformed dates are present
    assert (pd.to_numeric(dirty["spend"], errors="coerce") < 0).any()
    assert pd.to_datetime(dirty["date"], format="%Y-%m-%d", errors="coerce").isna().any()
    # at least one required field became null
    assert dirty[["channel", "region", "device"]].isna().any().any()


def test_ab_variant_has_higher_conversion_rate():
    # The injected lift should show up as a higher realised CVR for creative_B at scale.
    camps = G.build_campaigns(_rng())
    df = G.build_impressions(_rng(), camps, n_total=400_000)
    ab = df[df["campaign"] == C.AB_CAMPAIGN]
    agg = ab.groupby("creative")[["conversions", "clicks"]].sum()
    cvr = agg["conversions"] / agg["clicks"]
    assert cvr["creative_B"] > cvr["creative_A"]
