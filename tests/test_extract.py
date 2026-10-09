"""Tests for src/extract.py on the synthetic charts in samples/."""

import json
from pathlib import Path

import cv2
import pytest

from src.extract import detect_plot_area, extract_line_pixels

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
CHARTS = sorted(p for p in SAMPLES_DIR.glob("chart_*.png"))
TOLERANCE_PX = 3


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_detect_plot_area(chart_path):
    img = cv2.imread(str(chart_path))
    meta = json.loads(chart_path.with_name(f"{chart_path.stem}_meta.json").read_text())
    truth = meta["plot_bbox_px"]

    detected = dict(zip(("left", "top", "right", "bottom"), detect_plot_area(img)))
    diffs = {edge: detected[edge] - truth[edge] for edge in detected}
    bad = {edge: round(d, 1) for edge, d in diffs.items() if abs(d) > TOLERANCE_PX}

    if bad:
        print(f"FAIL {chart_path.stem}: off by {bad}")
    assert not bad, f"{chart_path.stem}: edges off by more than {TOLERANCE_PX}px: {bad}"


@pytest.mark.parametrize("chart_path", CHARTS, ids=[p.stem for p in CHARTS])
def test_extract_line_pixels(chart_path):
    img = cv2.imread(str(chart_path))
    left, top, right, bottom = detect_plot_area(img)
    inset = 3

    # Must not raise, whether the line is coloured or black.
    px_x, px_y, mode = extract_line_pixels(img, (left, top, right, bottom), inset=inset)
    print(f"{chart_path.stem}: mode={mode}")
    assert mode in ("color", "dark")

    # The line must stay strictly inside the inset crop. If the mask had picked
    # up an axis line, the per-column median would sit on the crop boundary.
    assert px_x.min() >= left + inset and px_x.max() < right - inset
    assert px_y.min() > top + inset, f"{chart_path.stem}: line touches the top edge"
    assert px_y.max() < bottom - inset, f"{chart_path.stem}: line touches the x axis"
