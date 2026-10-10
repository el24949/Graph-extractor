"""Draw the extracted line over the original chart, for visual checking.

Run from the project root to save overlays for all samples to docs/overlays/:
    python -m src.overlay
"""

from pathlib import Path

import cv2
import numpy as np

from src.pipeline import extract_series

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples"
OUT_DIR = ROOT / "docs" / "overlays"


def draw_overlay(img_bgr, px_x, px_y, thickness=1):
    """Return a copy of img_bgr with the pixel path (px_x, px_y) drawn in red."""
    out = img_bgr.copy()
    points = np.round(np.column_stack([px_x, px_y])).astype(np.int32)
    cv2.polylines(out, [points], isClosed=False, color=(0, 0, 255), thickness=thickness, lineType=cv2.LINE_AA)
    return out


def main():
    """Save an overlay for every sample chart to docs/overlays/."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for img_path in sorted(SAMPLES_DIR.glob("chart_[0-9][0-9].png")):
        df, mode, _ = extract_series(img_path)
        overlay = draw_overlay(cv2.imread(str(img_path)), df["px_x"], df["px_y"])
        out_path = OUT_DIR / f"{img_path.stem}_overlay.png"
        cv2.imwrite(str(out_path), overlay)
        print(f"{out_path.relative_to(ROOT)} (mode={mode})")


if __name__ == "__main__":
    main()
