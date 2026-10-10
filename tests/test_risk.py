"""Tests for P(wrong) and its bootstrap confidence intervals in src/risk.py."""

import json
from pathlib import Path

import numpy as np
import pytest

from src.forecast import MODELS, resample_series
from src.pipeline import extract_series
from src.risk import bootstrap_ci, forecast_with_risk, p_wrong, p_wrong_by_horizon

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# 4 windows x 2 horizons. With tol 10, the wrong ones are 20, 30, 40:
# 3 of 8 overall, 0/4 at horizon 1, 3/4 at horizon 2.
KNOWN = np.array([[1, 20], [2, 30], [3, 5], [4, 40]], dtype=float)


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
    assert np.all((0 <= result["ci_low"]) & (result["ci_low"] <= result["p_wrong"]))
    assert np.all((result["p_wrong"] <= result["ci_high"]) & (result["ci_high"] <= 1))
