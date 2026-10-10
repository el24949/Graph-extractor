"""End-to-end accuracy: detect, extract and calibrate each sample chart, then
compare against the ground truth in samples/chart_XX_truth.csv."""

import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from src.calibrate import calibrate, pixel_to_value
from src.extract import detect_plot_area, extract_line_pixels

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
CHARTS = sorted(SAMPLES_DIR.glob("chart_*.png"))
MAX_RMSE_PCT = 5.0


def test_pixel_to_value_flipped_axis():
    # Image y grows downward while data y grows upward:
    # pixel 400 (bottom) -> 0, pixel 100 (top) -> 30.
    assert pixel_to_value(400, 400, 0, 100, 30) == pytest.approx(0)
    assert pixel_to_value(100, 400, 0, 100, 30) == pytest.approx(30)
    assert pixel_to_value(250, 400, 0, 100, 30) == pytest.approx(15)
    # Smaller pixel y means a larger value.
    np.testing.assert_allclose(pixel_to_value([400, 300, 200], 400, 0, 100, 30), [0, 10, 20])


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_end_to_end_rmse(chart_path):
    img = cv2.imread(str(chart_path))
    meta = json.loads(chart_path.with_name(f"{chart_path.stem}_meta.json").read_text())
    truth = pd.read_csv(chart_path.with_name(f"{chart_path.stem}_truth.csv"))

    left, top, right, bottom = detect_plot_area(img)
    px_x, px_y, mode = extract_line_pixels(img, (left, top, right, bottom))

    # Detected box edges give the pixel refs; meta axis limits give the values.
    # y refs run bottom -> ymin, top -> ymax, which flips the image y axis.
    x_vals, y_vals = calibrate(
        px_x,
        px_y,
        x_ref=((left, meta["xmin"]), (right, meta["xmax"])),
        y_ref=((bottom, meta["ymin"]), (top, meta["ymax"])),
    )

    # Resample the extracted line at the true x positions and compare.
    y_pred = np.interp(truth["x"], x_vals, y_vals)
    rmse = np.sqrt(np.mean((y_pred - truth["y"]) ** 2))
    rmse_pct = 100 * rmse / (meta["ymax"] - meta["ymin"])

    print(f"{chart_path.stem}: RMSE {rmse_pct:.2f}% of y-range (mode={mode})")
    assert rmse_pct < MAX_RMSE_PCT, f"{chart_path.stem}: RMSE {rmse_pct:.2f}% >= {MAX_RMSE_PCT}%"
