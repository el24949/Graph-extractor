"""Plot-area detection on the harder synthetic variants in samples/robust/:
a dark frame around the image, mid-gray axes, gridlines only, and a full box,
plus the line-isolation variants (two lines, legend, line ending early).

Same rule as tests/test_extract.py: every edge within 3 px of the meta box.
"""

import json
from pathlib import Path

import cv2
import pytest

from src.extract import find_plot_area, validate_box

ROBUST_DIR = Path(__file__).resolve().parent.parent / "samples" / "robust"
CHARTS = sorted(ROBUST_DIR.glob("robust_[0-9][0-9].png"))
TOLERANCE_PX = 3

# The box comes from gridlines only when the chart has no axis lines.
EXPECTED_MODE = {
    "frame": "axes",
    "gray_axes": "axes",
    "grid_only": "grid",
    "full_box": "axes",
    # Line-isolation variants (tests/test_series.py); their boxes are checked here too.
    "two_lines": "axes",
    "legend": "axes",
    "ends_early": "axes",
}


def test_robust_samples_exist():
    variants = {json.loads(p.with_name(f"{p.stem}_meta.json").read_text())["variant"] for p in CHARTS}
    assert variants == set(EXPECTED_MODE), "run: python -m src.generate_samples --robust"


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_robust_plot_area(chart_path):
    img = cv2.imread(str(chart_path))
    meta = json.loads(chart_path.with_name(f"{chart_path.stem}_meta.json").read_text())
    truth = meta["plot_bbox_px"]

    box, mode = find_plot_area(img)
    detected = dict(zip(("left", "top", "right", "bottom"), box))
    bad = {edge: round(detected[edge] - truth[edge], 1) for edge in detected if abs(detected[edge] - truth[edge]) > TOLERANCE_PX}

    if bad:
        print(f"FAIL {chart_path.stem} ({meta['variant']}): off by {bad}")
    assert not bad, f"{chart_path.stem} ({meta['variant']}): edges off by more than {TOLERANCE_PX}px: {bad}"
    assert mode == EXPECTED_MODE[meta["variant"]]


@pytest.mark.parametrize(
    "box, message",
    [
        ((100, 300, 700, 200), "bottom"),  # bottom above top
        ((100, 100, 100, 300), "left"),  # zero width
        ((700, 100, 100, 300), "left"),  # left right of right
        ((100, 100, 140, 300), "too small"),  # 40 px wide in an 800 px image
        ((100, 100, 700, 120), "too small"),  # 20 px tall in a 400 px image
        ((2, 2, 798, 398), "whole"),  # almost the entire image
    ],
)
def test_validate_box_rejects(box, message):
    with pytest.raises(ValueError, match=message):
        validate_box(box, (400, 800, 3))


def test_validate_box_accepts_normal_box():
    validate_box((43, 15, 786, 361), (400, 800, 3))  # chart_01's box


def test_blank_image_raises_clear_error():
    blank = cv2.imread(str(CHARTS[0]))
    blank[:] = 255
    with pytest.raises(ValueError, match="No plot area found"):
        find_plot_area(blank)
