"""Manual plot box: extract_series(box=...) and the --box CLI option."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import extract_series, validate_manual_box

ROOT = Path(__file__).resolve().parent.parent
CHARTS = sorted((ROOT / "samples").glob("chart_[0-9][0-9].png"))
MAX_RMSE_PCT = 5.0


def meta_of(p):
    return json.loads(p.with_name(f"{p.stem}_meta.json").read_text())


def true_box(meta):
    b = meta["plot_bbox_px"]
    return tuple(int(round(b[k])) for k in ("left", "top", "right", "bottom"))


def rmse_pct(p, box=None):
    meta = meta_of(p)
    truth = pd.read_csv(p.with_name(f"{p.stem}_truth.csv"))
    df, _, used_box, box_mode = extract_series(p, (meta["xmin"], meta["xmax"]), (meta["ymin"], meta["ymax"]), box=box)
    err = np.interp(truth["x"], df["x"], df["y"]) - truth["y"]
    return 100 * np.sqrt(np.mean(err**2)) / (meta["ymax"] - meta["ymin"]), used_box, box_mode


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_manual_box_equal_to_auto_box_gives_identical_output(chart_path):
    meta = meta_of(chart_path)
    limits = ((meta["xmin"], meta["xmax"]), (meta["ymin"], meta["ymax"]))
    auto_df, auto_mode, auto_box, _ = extract_series(chart_path, *limits)
    manual_df, manual_mode, manual_box, box_mode = extract_series(chart_path, *limits, box=auto_box)

    assert box_mode == "manual"
    assert manual_box == auto_box and manual_mode == auto_mode
    pd.testing.assert_frame_equal(manual_df, auto_df)


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_manual_true_box_rmse(chart_path):
    # The true box comes from the meta file (rounded to whole pixels). The auto
    # box is up to 1 px off (its right edge is 1 px too far right on every
    # chart), so the two RMSEs are close but not identical: the true box is
    # never worse.
    auto, auto_box, _ = rmse_pct(chart_path)
    manual, manual_box, box_mode = rmse_pct(chart_path, box=true_box(meta_of(chart_path)))
    print(f"{chart_path.stem}: auto {auto:.2f}% {auto_box} | manual true box {manual:.2f}% {manual_box}")

    assert box_mode == "manual"
    assert manual < MAX_RMSE_PCT
    assert manual <= auto + 0.01


@pytest.mark.parametrize(
    "box, message",
    [
        ((100, 50, 100, 300), "right .* greater than left"),
        ((300, 50, 100, 300), "right .* greater than left"),
        ((100, 300, 500, 300), "bottom .* greater than top"),
        ((-1, 50, 500, 300), "inside the image"),
        ((100, 50, 800, 300), "inside the image"),  # chart_01 is 800 px wide: max index 799
        ((100, 50, 500, 400), "inside the image"),  # and 400 px tall
        ((100, 50, 105, 300), "too small"),
        ((100, 50, 500), "four values"),
        ((100.5, 50, 500, 300), "whole pixel"),
        (("a", 50, 500, 300), "whole pixel"),
    ],
)
def test_invalid_manual_box_raises_clear_error(box, message):
    with pytest.raises(ValueError, match=f"Invalid manual box.*{message}"):
        extract_series(CHARTS[0], box=box)


def test_validate_manual_box_accepts_full_image():
    # A tightly cropped chart may fill the image; manual boxes allow that.
    assert validate_manual_box((0, 0, 799, 399), (400, 800, 3)) == (0, 0, 799, 399)


def test_cli_box_option(tmp_path):
    chart = CHARTS[0]
    box = true_box(meta_of(chart))
    out = tmp_path / "out.csv"
    ok = subprocess.run(
        [sys.executable, "-m", "src.pipeline", str(chart), "--box", *map(str, box), "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert "plot area from manual" in ok.stdout
    assert len(pd.read_csv(out)) > 0

    bad = subprocess.run(
        [sys.executable, "-m", "src.pipeline", str(chart), "--box", "500", "50", "100", "300", "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert "Invalid manual box" in bad.stderr
