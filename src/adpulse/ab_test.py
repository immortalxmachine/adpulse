"""A/B test analysis for two ad creatives.

Primary test: two-proportion z-test on conversion rate (statsmodels), with a Wald
confidence interval on the difference, a power / sample-size check, and a plain-language
conclusion. A chi-square test of independence is included as an independent cross-check;
on a 2x2 table it should agree with the z-test (chi2 ~= z^2).

Every function is pure (numbers in, numbers out) so the statistics can be unit-tested
against hand-worked or textbook values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from scipy.stats import chi2_contingency
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_effectsize,
    proportions_ztest,
)


@dataclass
class ABResult:
    """Outcome of the two-proportion z-test. 'a' = control, 'b' = variant."""

    n_a: int
    n_b: int
    conv_a: int
    conv_b: int
    rate_a: float
    rate_b: float
    abs_lift: float          # rate_b - rate_a (percentage points, as a proportion)
    rel_lift: float          # (rate_b - rate_a) / rate_a
    z_stat: float
    p_value: float
    ci_low: float            # 95% CI lower bound on (rate_b - rate_a)
    ci_high: float
    alpha: float
    significant: bool

    def as_dict(self) -> dict:
        return asdict(self)


def two_proportion_ztest(
    conv_a: int, n_a: int, conv_b: int, n_b: int, alpha: float = 0.05
) -> ABResult:
    """Pooled two-sided two-proportion z-test comparing variant B against control A."""
    rate_a = conv_a / n_a
    rate_b = conv_b / n_b

    # statsmodels: counts/nobs ordered [B, A]; default is a pooled, two-sided z-test.
    z_stat, p_value = proportions_ztest(count=[conv_b, conv_a], nobs=[n_b, n_a])

    # Wald CI for the difference p_b - p_a.
    ci_low, ci_high = confint_proportions_2indep(
        count1=conv_b, nobs1=n_b, count2=conv_a, nobs2=n_a, method="wald", alpha=alpha
    )

    return ABResult(
        n_a=int(n_a),
        n_b=int(n_b),
        conv_a=int(conv_a),
        conv_b=int(conv_b),
        rate_a=float(rate_a),
        rate_b=float(rate_b),
        abs_lift=float(rate_b - rate_a),
        rel_lift=float((rate_b - rate_a) / rate_a) if rate_a else float("nan"),
        z_stat=float(z_stat),
        p_value=float(p_value),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        alpha=alpha,
        significant=bool(p_value < alpha),
    )


def chi_square_test(conv_a: int, n_a: int, conv_b: int, n_b: int) -> dict[str, float]:
    """Chi-square test of independence on the 2x2 (variant x converted) table."""
    table = [
        [conv_b, n_b - conv_b],  # variant B: converted, not converted
        [conv_a, n_a - conv_a],  # control A: converted, not converted
    ]
    chi2, p_value, dof, _expected = chi2_contingency(table, correction=False)
    return {"chi2": float(chi2), "p_value": float(p_value), "dof": int(dof)}


def observed_power(rate_a: float, rate_b: float, n_per_group: int, alpha: float = 0.05) -> float:
    """Statistical power of the realised test at the observed rates and sample size."""
    effect = proportion_effectsize(rate_b, rate_a)  # Cohen's h
    return float(
        NormalIndPower().solve_power(
            effect_size=effect, nobs1=n_per_group, alpha=alpha, ratio=1.0, alternative="two-sided"
        )
    )


def required_sample_size(
    rate_a: float, rel_mde: float, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Sample size PER GROUP needed to detect a relative lift ``rel_mde`` at given power."""
    rate_b = rate_a * (1.0 + rel_mde)
    effect = proportion_effectsize(rate_b, rate_a)
    n = NormalIndPower().solve_power(
        effect_size=effect, alpha=alpha, power=power, ratio=1.0, alternative="two-sided"
    )
    return int(-(-n // 1))  # ceil


def conclude(result: ABResult) -> str:
    """One-paragraph, non-statistician-friendly verdict."""
    direction = "higher" if result.abs_lift > 0 else "lower"
    verb = "is" if result.significant else "is NOT"
    return (
        f"Creative B converted at {result.rate_b:.3%} vs creative A at {result.rate_a:.3%} "
        f"({result.rel_lift:+.1%} relative, {direction}). This difference {verb} statistically "
        f"significant at alpha={result.alpha:g} (z={result.z_stat:.2f}, p={result.p_value:.4g}). "
        f"The 95% confidence interval for the absolute lift is "
        f"[{result.ci_low:+.4f}, {result.ci_high:+.4f}]."
    )
