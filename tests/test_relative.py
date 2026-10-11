"""Optional axis limits: relative units (0-100% of the plot box) by default."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.forecast import MODELS, resample_series
from src.pipeline import UNITS_DATA, UNITS_PIXELS, UNITS_RELATIVE, extract_series
from src.risk import forecast_with_risk

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples"
CHARTS = sorted(SAMPLES_DIR.glob("chart_[0-9][0-9].png"))


def limits_of(p):
    meta = json.loads(p.with_name(f"{p.stem}_meta.json").read_text())
    return (meta["xmin"], meta["xmax"]), (meta["ymin"], meta["ymax"])


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_relative_units_by_default(chart_path):
    df, _, box, _ = extract_series(chart_path)
    left, top, right, bottom = box

    assert list(df.columns) == ["x", "y"]
    assert df.attrs["units"] == UNITS_RELATIVE
    # The line lies inside the box, so relative values lie inside 0-100.
    assert df["x"].between(0, 100).all() and df["y"].between(0, 100).all()
    # Same as giving the limits (0, 100) for both axes.
    same, *_ = extract_series(chart_path, (0, 100), (0, 100))
    assert same.attrs["units"] == UNITS_DATA
    pd.testing.assert_frame_equal(df, same)


def test_relative_is_an_affine_map_of_real_values():
    path = SAMPLES_DIR / "chart_04.png"
    (xmin, xmax), (ymin, ymax) = limits_of(path)
    rel, *_ = extract_series(path)
    real, *_ = extract_series(path, (xmin, xmax), (ymin, ymax))
    np.testing.assert_allclose(real["x"], xmin + rel["x"] / 100 * (xmax - xmin))
    np.testing.assert_allclose(real["y"], ymin + rel["y"] / 100 * (ymax - ymin))


def test_pixels_option_keeps_the_pixel_path():
    path = SAMPLES_DIR / "chart_04.png"
    px, _, (left, top, right, bottom), _ = extract_series(path, pixels=True)
    rel, *_ = extract_series(path)

    assert list(px.columns) == ["px_x", "px_y"] and px.attrs["units"] == UNITS_PIXELS
    np.testing.assert_allclose(rel["x"], (px["px_x"] - left) / (right - left) * 100)
    np.testing.assert_allclose(rel["y"], (bottom - px["px_y"]) / (bottom - top) * 100)
    with pytest.raises(ValueError, match="pixels=True"):
        extract_series(path, (0, 1), (0, 1), pixels=True)


def risk_in_both_units(path):
    rel_df, *_ = extract_series(path)
    real_df, *_ = extract_series(path, *limits_of(path))
    _, y_rel = resample_series(rel_df["x"], rel_df["y"], n=100)
    _, y_real = resample_series(real_df["x"], real_df["y"], n=100)
    return forecast_with_risk(y_rel, MODELS, tol_pct=10), forecast_with_risk(y_real, MODELS, tol_pct=10)


# P(wrong) is measured as a % of the training range, so it should not depend on
# the units. A silent fallback to naive would hide a difference, so fail on it.
@pytest.mark.filterwarnings("error:.*using naive forecast")
def test_p_wrong_and_model_identical_with_relative_and_real_units():
    rel, real = risk_in_both_units(SAMPLES_DIR / "chart_04.png")
    print(f"\nchart_04: model {rel['model']} / {real['model']}, P(wrong) {rel['p_wrong_overall']:.3f} / {real['p_wrong_overall']:.3f}")

    assert rel["model"] == real["model"]
    np.testing.assert_array_equal(rel["p_wrong"], real["p_wrong"])
    np.testing.assert_array_equal(rel["ci_low"], real["ci_low"])
    np.testing.assert_array_equal(rel["ci_high"], real["ci_high"])
    assert rel["p_wrong_overall"] == real["p_wrong_overall"]
    assert rel["overall_ci"] == real["overall_ci"]


# Exact equality does not hold on every chart: naive is exactly scale-free, but
# the ETS and ARIMA fits (statsmodels) converge slightly differently on rescaled
# data, and on chart_09 ARIMA fails to converge (falling back to naive) in a
# different number of windows. Measured on the 15 charts: same model on all 15,
# identical P(wrong) on 12; on chart_05, chart_09 and chart_13 one window per
# step at most crosses the tolerance (31 windows: up to 0.032 per step, 0.022
# overall).
@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_model_same_and_p_wrong_close_on_all_charts(chart_path):
    rel, real = risk_in_both_units(chart_path)
    one_window = 1 / 31

    assert rel["model"] == real["model"]
    assert np.abs(rel["p_wrong"] - real["p_wrong"]).max() <= one_window + 1e-9
    assert abs(rel["p_wrong_overall"] - real["p_wrong_overall"]) <= 0.03


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.pipeline", str(SAMPLES_DIR / "chart_04.png"), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_reports_relative_units(tmp_path):
    out = tmp_path / "out.csv"
    result = run_cli("--out", out)
    assert result.returncode == 0, result.stderr
    assert "Units: relative" in result.stdout
    expected, *_ = extract_series(SAMPLES_DIR / "chart_04.png")
    pd.testing.assert_frame_equal(pd.read_csv(out), expected, check_exact=False, rtol=1e-12)


def test_cli_pixels_and_real_units(tmp_path):
    out = tmp_path / "px.csv"
    result = run_cli("--pixels", "--out", out)
    assert result.returncode == 0, result.stderr
    assert "Units: pixels" in result.stdout and list(pd.read_csv(out).columns) == ["px_x", "px_y"]

    result = run_cli("--xmin", 0, "--xmax", 299, "--ymin", -33.77, "--ymax", 62.76, "--out", tmp_path / "real.csv")
    assert result.returncode == 0, result.stderr
    assert "Units: axis values" in result.stdout

    result = run_cli("--pixels", "--xmin", 0, "--xmax", 1, "--ymin", 0, "--ymax", 1, "--out", out)
    assert result.returncode != 0 and "--pixels cannot be combined" in result.stderr
