"""Tests for P(wrong) and its confidence intervals in src/risk.py.

Per-step intervals are Wilson; the overall interval is a bootstrap over windows.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from src.forecast import MODELS, resample_series
from src.pipeline import extract_series
from src.risk import bootstrap_ci, forecast_with_risk, p_wrong, p_wrong_by_horizon, wilson_ci

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# 4 windows x 2 horizons. With tol 10, the wrong ones are 20, 30, 40:
# 3 of 8 overall, 0/4 at horizon 1, 3/4 at horizon 2.
KNOWN = np.array([[1, 20], [2, 30], [3, 5], [4, 40]], dtype=float)

# Wilson bounds can land a rounding error (~1e-16) past p at p = 0 or 1
# (e.g. upper = 0.9999999999999999 when p = 1), so containment uses this slack.
EPS = 1e-12


def errors_with_misses(misses, n_windows, h=1, tol=10.0):
    """Error matrix where the first `misses` windows exceed tol at every step."""
    errors = np.zeros((n_windows, h))
    errors[:misses] = tol + 1
    return errors


def test_known_case():
    assert p_wrong(KNOWN, 10) == pytest.approx(0.375)
    np.testing.assert_allclose(p_wrong_by_horizon(KNOWN, 10), [0, 0.75])


def test_ci_contains_point_estimate():
    lo, hi = bootstrap_ci(KNOWN, 10)
    assert lo <= p_wrong(KNOWN, 10) <= hi
    assert lo <= hi

    lo_h, hi_h = bootstrap_ci(KNOWN, 10, axis=0)
    p_h = p_wrong_by_horizon(KNOWN, 10)
    assert np.all(lo_h <= p_h) and np.all(p_h <= hi_h)
    assert np.all(lo_h <= hi_h)


def test_extreme_tolerances():
    assert p_wrong(KNOWN, 1000) == 0
    lo, hi = bootstrap_ci(KNOWN, 1000)
    assert (lo, hi) == (0, 0)

    assert p_wrong(KNOWN, 0) == 1


def test_same_seed_same_ci():
    first = bootstrap_ci(KNOWN, 10, axis=0, seed=42)
    second = bootstrap_ci(KNOWN, 10, axis=0, seed=42)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])


def test_wilson_zero_misses_out_of_31():
    lo, hi = wilson_ci(errors_with_misses(0, 31, h=10), 10)
    np.testing.assert_allclose(lo, 0, atol=EPS)
    assert np.all((0.10 < hi) & (hi < 0.12))


@pytest.mark.parametrize("n_windows", [1, 4, 31, 200])
def test_wilson_contains_point_estimate(n_windows):
    for misses in range(n_windows + 1):
        errors = errors_with_misses(misses, n_windows)
        lo, hi = wilson_ci(errors, 10)
        p = p_wrong_by_horizon(errors, 10)
        assert np.all(lo <= p + EPS) and np.all(p <= hi + EPS), f"{misses}/{n_windows}: [{lo}, {hi}] vs {p}"
        assert np.all((0 <= lo) & (lo <= hi) & (hi <= 1))


def test_wilson_known_case():
    lo, hi = wilson_ci(KNOWN, 10)
    p = p_wrong_by_horizon(KNOWN, 10)
    assert np.all(lo <= p + EPS) and np.all(p <= hi + EPS)
    # Unlike the bootstrap, 0 misses out of 4 still gives a non-zero upper bound.
    assert hi[0] > 0


# A silent fallback to naive would change which model wins, so fail on it.
@pytest.mark.filterwarnings("error:.*using naive forecast")
def test_forecast_with_risk_on_chart_04():
    img_path = SAMPLES_DIR / "chart_04.png"
    meta = json.loads((SAMPLES_DIR / "chart_04_meta.json").read_text())
    df, _, _ = extract_series(img_path, (meta["xmin"], meta["xmax"]), (meta["ymin"], meta["ymax"]))
    _, y = resample_series(df["x"], df["y"], n=100)

    result = forecast_with_risk(y, MODELS, tol_pct=10)

    lo_all, hi_all = result["overall_ci"]
    print(f"\nchart_04: chosen model = {result['model']}")
    print(f"overall P(wrong) = {result['p_wrong_overall']:.2f}  95% CI [{lo_all:.2f}, {hi_all:.2f}]")
    print("step  forecast  P(wrong)  95% CI")
    for k in range(10):
        print(
            f"{k + 1:>4}  {result['forecast'][k]:8.2f}  {result['p_wrong'][k]:8.2f}"
            f"  [{result['ci_low'][k]:.2f}, {result['ci_high'][k]:.2f}]"
        )

    assert result["model"] in MODELS
    assert result["forecast"].shape == result["p_wrong"].shape == (10,)
    lo, hi, p = result["ci_low"], result["ci_high"], result["p_wrong"]
    assert np.all((0 <= lo) & (lo <= p + EPS)) and np.all((p <= hi + EPS) & (hi <= 1))

    # Per-step CIs are Wilson: step 1 has 0 misses in 31 windows, so the
    # upper bound is about 0.11, not the bootstrap's degenerate 0.
    assert p[0] == 0
    assert 0.10 < hi[0] < 0.12
    # The overall CI is still the bootstrap over windows.
    assert lo_all <= result["p_wrong_overall"] <= hi_all
