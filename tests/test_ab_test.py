"""Unit tests for the A/B test statistics."""

import math

from adpulse import ab_test


def test_clear_difference_is_significant():
    # 1000/10000 = 10% vs 1300/10000 = 13%; a large, obvious difference.
    res = ab_test.two_proportion_ztest(conv_a=1000, n_a=10_000, conv_b=1300, n_b=10_000)
    assert math.isclose(res.rate_a, 0.10, abs_tol=1e-9)
    assert math.isclose(res.rate_b, 0.13, abs_tol=1e-9)
    assert res.abs_lift > 0
    assert res.significant
    assert res.p_value < 0.05
    # CI for a clearly positive lift should not contain 0
    assert res.ci_low > 0


def test_no_difference_is_not_significant():
    res = ab_test.two_proportion_ztest(conv_a=500, n_a=10_000, conv_b=505, n_b=10_000)
    assert not res.significant
    assert res.p_value > 0.05


def test_chi_square_agrees_with_ztest_on_2x2():
    # On a 2x2 table, chi-square statistic ~= z^2 (both uncorrected).
    a, na, b, nb = 1000, 10_000, 1300, 10_000
    res = ab_test.two_proportion_ztest(a, na, b, nb)
    chi = ab_test.chi_square_test(a, na, b, nb)
    assert math.isclose(chi["chi2"], res.z_stat**2, rel_tol=1e-6)
    assert chi["dof"] == 1


def test_required_sample_size_grows_as_mde_shrinks():
    big_mde = ab_test.required_sample_size(rate_a=0.09, rel_mde=0.20)
    small_mde = ab_test.required_sample_size(rate_a=0.09, rel_mde=0.05)
    assert small_mde > big_mde > 0


def test_observed_power_in_unit_interval():
    p = ab_test.observed_power(rate_a=0.10, rate_b=0.13, n_per_group=10_000)
    assert 0.0 <= p <= 1.0
    assert p > 0.9  # this effect/size should be very well powered
