"""Reference-tick calibration: extract_series(x_ticks=..., y_ticks=...) and --xtick/--ytick."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import extract_series

ROOT = Path(__file__).resolve().parent.parent
CHARTS = sorted((ROOT / "samples").glob("chart_[0-9][0-9].png"))
MAX_RMSE_PCT = 5.0


def meta_of(p):
    return json.loads(p.with_name(f"{p.stem}_meta.json").read_text())


def limits_of(meta):
    return (meta["xmin"], meta["xmax"]), (meta["ymin"], meta["ymax"])


def box_edge_value(p, edge1, v1, edge2, v2):
    """The value the box-edge calibration gives pixel p (edge1 -> v1, edge2 -> v2)."""
    return v1 + (p - edge1) * (v2 - v1) / (edge2 - edge1)


def ticks_inside(box, x_ref, y_ref):
    """Two ticks per axis at 25% and 75% inside the box, valued as the box-edge calibration values them."""
    left, top, right, bottom = box
    xs = (left + 0.25 * (right - left), left + 0.75 * (right - left))
    ys = (bottom - 0.25 * (bottom - top), bottom - 0.75 * (bottom - top))
    x_ticks = tuple((p, box_edge_value(p, left, x_ref[0], right, x_ref[1])) for p in xs)
    y_ticks = tuple((p, box_edge_value(p, bottom, y_ref[0], top, y_ref[1])) for p in ys)
    return x_ticks, y_ticks


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_ticks_inside_match_box_edge_calibration(chart_path):
    x_ref, y_ref = limits_of(meta_of(chart_path))
    box_df, mode, box, box_mode = extract_series(chart_path, x_ref, y_ref)
    x_ticks, y_ticks = ticks_inside(box, x_ref, y_ref)
    tick_df, tick_mode, tick_box, tick_box_mode = extract_series(chart_path, x_ticks=x_ticks, y_ticks=y_ticks)

    assert (tick_mode, tick_box, tick_box_mode) == (mode, box, box_mode)
    pd.testing.assert_frame_equal(tick_df, box_df, check_exact=False, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_ticks_at_true_positions_beat_auto_box_edges(chart_path):
    # Ticks placed at whole pixels inside the true plot box (from the meta file)
    # do not depend on where the box edges are detected, so they avoid the auto
    # box's 1 px error on the right edge: never worse than box-edge calibration.
    meta = meta_of(chart_path)
    b = meta["plot_bbox_px"]
    x_ref, y_ref = limits_of(meta)
    truth = pd.read_csv(chart_path.with_name(f"{chart_path.stem}_truth.csv"))

    xs = (round(b["left"] + 0.1 * (b["right"] - b["left"])), round(b["right"] - 0.1 * (b["right"] - b["left"])))
    ys = (round(b["bottom"] - 0.1 * (b["bottom"] - b["top"])), round(b["top"] + 0.1 * (b["bottom"] - b["top"])))
    x_ticks = tuple((p, box_edge_value(p, b["left"], x_ref[0], b["right"], x_ref[1])) for p in xs)
    y_ticks = tuple((p, box_edge_value(p, b["bottom"], y_ref[0], b["top"], y_ref[1])) for p in ys)

    def rmse(df):
        err = np.interp(truth["x"], df["x"], df["y"]) - truth["y"]
        return 100 * np.sqrt(np.mean(err**2)) / (y_ref[1] - y_ref[0])

    box_rmse = rmse(extract_series(chart_path, x_ref, y_ref)[0])
    tick_rmse = rmse(extract_series(chart_path, x_ticks=x_ticks, y_ticks=y_ticks)[0])
    print(f"{chart_path.stem}: box edges {box_rmse:.2f}% | true ticks {tick_rmse:.2f}%")

    assert tick_rmse < MAX_RMSE_PCT
    assert tick_rmse <= box_rmse + 0.01


def test_ticks_work_with_a_manual_box():
    meta = meta_of(CHARTS[0])
    x_ref, y_ref = limits_of(meta)
    _, _, box, _ = extract_series(CHARTS[0])
    box_df, *_ = extract_series(CHARTS[0], x_ref, y_ref, box=box)
    x_ticks, y_ticks = ticks_inside(box, x_ref, y_ref)
    tick_df, _, _, box_mode = extract_series(CHARTS[0], x_ticks=x_ticks, y_ticks=y_ticks, box=box)

    assert box_mode == "manual"
    pd.testing.assert_frame_equal(tick_df, box_df, check_exact=False, rtol=1e-9, atol=1e-9)


GOOD = ((100, 0), (500, 10))


@pytest.mark.parametrize(
    "x_ticks, y_ticks, message",
    [
        (((100, 0), (100, 10)), GOOD, "Invalid x ticks.*pixels must be different"),
        (GOOD, ((200, 0), (200, 5)), "Invalid y ticks.*pixels must be different"),
        (((100, 3), (500, 3)), GOOD, "Invalid x ticks.*values must be different"),
        (((100, 0),), GOOD, "Invalid x ticks.*two \\(pixel, value\\) pairs"),
        (((100, 0), (500, 10), (600, 20)), GOOD, "Invalid x ticks.*two \\(pixel, value\\) pairs"),
        (((100, "a"), (500, 10)), GOOD, "Invalid x ticks.*two \\(pixel, value\\) pairs"),
        (GOOD, ((100, float("nan")), (300, 10)), "Invalid y ticks.*finite"),
    ],
)
def test_invalid_ticks_raise_clear_error(x_ticks, y_ticks, message):
    with pytest.raises(ValueError, match=message):
        extract_series(CHARTS[0], x_ticks=x_ticks, y_ticks=y_ticks)


def test_ticks_need_both_axes_and_not_limits():
    with pytest.raises(ValueError, match="both x_ticks and y_ticks"):
        extract_series(CHARTS[0], x_ticks=GOOD)
    with pytest.raises(ValueError, match="not both"):
        extract_series(CHARTS[0], (0, 1), (0, 1), x_ticks=GOOD, y_ticks=GOOD)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.pipeline", str(CHARTS[0]), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_ticks_match_python_api(tmp_path):
    x_ref, y_ref = limits_of(meta_of(CHARTS[0]))
    _, _, box, _ = extract_series(CHARTS[0])
    x_ticks, y_ticks = ticks_inside(box, x_ref, y_ref)
    out = tmp_path / "out.csv"
    flags = [f for (p, v) in x_ticks for f in ("--xtick", repr(p), repr(v))]
    flags += [f for (p, v) in y_ticks for f in ("--ytick", repr(p), repr(v))]
    result = run_cli(*flags, "--out", out)

    assert result.returncode == 0, result.stderr
    expected, *_ = extract_series(CHARTS[0], x_ticks=x_ticks, y_ticks=y_ticks)
    pd.testing.assert_frame_equal(pd.read_csv(out), expected, check_exact=False, rtol=1e-9)


@pytest.mark.parametrize(
    "args, message",
    [
        (["--xtick", 100, 0, "--ytick", 300, 0, "--ytick", 50, 10], "exactly twice"),
        (["--xtick", 100, 0, "--xtick", 500, 10], "exactly twice"),
        (["--xtick", 100, 0, "--xtick", 500, 10, "--ytick", 300, 0, "--ytick", 50, 10, "--xmin", 0], "not both"),
        (["--xtick", 100, 0, "--xtick", 100, 10, "--ytick", 300, 0, "--ytick", 50, 10], "pixels must be different"),
    ],
)
def test_cli_rejects_bad_ticks(tmp_path, args, message):
    result = run_cli(*args, "--out", tmp_path / "out.csv")
    assert result.returncode != 0
    assert message in result.stderr
