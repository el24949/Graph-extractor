"""Run the held-out real charts in samples/real_heldout/ and save overlays.

Run from the project root:
    python -m src.run_heldout            # the original held-out run (box-edge limits)
    python -m src.run_heldout --ticks    # the re-run with reference ticks (no longer held-out)

Normal flow: Auto plot box (Manual is not needed: Auto found a box on all
four). The line colour is the one chosen from the colour list before the
original run. Prints the box, colour, line mode and calibrated range for each
chart; overlays go to docs/overlays/real_heldout/. Results are written up by
hand in docs/real_heldout_results.md.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from src.pipeline import extract_series, series_colors

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples" / "real_heldout"
OUT_DIR = ROOT / "docs" / "overlays" / "real_heldout"

# Colour number from the --list-colors list (1 = largest), None = no colour (dark fallback).
COLOR = {"chart1": 1, "chart2": 1, "chart3": None, "chart4": 2}

# Original held-out run: limits read by eye from the tick labels (xmin, xmax, ymin, ymax),
# paired with the box edges. chart2 and chart3 xmin were marked uncertain.
LIMITS = {
    "chart1": (0, 5, 0, 6),
    "chart2": (0, 2015, 0, 25),
    "chart3": (0, 2006, 0, 12),
    "chart4": (1880, 2000, -0.4, 0.6),
}

# Re-run (post-hoc, no longer held-out): two reference ticks per axis,
# (pixel in the full image, value), measured from the tick marks or gridlines
# after the original run had been seen. See docs/real_heldout_results.md.
TICKS = {
    # x tick marks 1.0 and 5.0; y tick marks 1 and 6
    "chart1": (((103, 1.0), (553, 5.0)), ((410, 1.0), (74, 6.0))),
    # x tick marks 1916 and 2015; y tick marks 0 and 25 (light gray marks)
    "chart2": (((68, 1916), (536, 2015)), ((325, 0), (52, 25))),
    # no tick marks: the gridlines under the 2002 and 2006 dots (the labels are
    # centred 8-25 px further left); y gridlines at the 2 and 12 labels
    "chart3": (((287.5, 2002), (913.5, 2006)), ((695.5, 2), (158.5, 12))),
    # dotted gridlines at 1900 and 2000; at -0.4 and 0.4
    "chart4": (((268.4, 1900), (840.5, 2000)), ((628.0, -0.4), (160.0, 0.4))),
}


def draw(img, px, box, label, line_bgr, ticks=None):
    out = img.copy()
    left, top, right, bottom = box
    cv2.rectangle(out, (left, top), (right, bottom), (0, 180, 0), 1)
    if ticks:
        height, width = img.shape[:2]
        for p, _ in ticks[0]:
            cv2.line(out, (int(round(p)), 0), (int(round(p)), height - 1), (200, 80, 0), 1)
        for p, _ in ticks[1]:
            cv2.line(out, (0, int(round(p))), (width - 1, int(round(p))), (0, 140, 255), 1)
    points = np.round(np.column_stack([px["px_x"], px["px_y"]])).astype(np.int32)
    cv2.polylines(out, [points], isClosed=False, color=line_bgr, thickness=1, lineType=cv2.LINE_AA)
    cv2.putText(out, label, (5, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticks", action="store_true", help="calibrate from TICKS instead of the box-edge LIMITS")
    args = parser.parse_args()
    if args.ticks and not TICKS:
        parser.exit(1, "Error: TICKS is empty; fill in the reference ticks first\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in sorted(COLOR):
        path = SAMPLES_DIR / f"{name}.jpg"
        box, box_mode, colors = series_colors(path)
        idx = COLOR[name]
        hue = colors[idx - 1]["hue"] if idx else None
        hex_color = colors[idx - 1]["hex"] if idx else "none (dark fallback)"

        px, mode, box, box_mode = extract_series(path, target_hue=hue, pixels=True)
        if args.ticks:
            x_ticks, y_ticks = TICKS[name]
            df, *_ = extract_series(path, target_hue=hue, x_ticks=x_ticks, y_ticks=y_ticks)
        else:
            lim = LIMITS[name]
            df, *_ = extract_series(path, (lim[0], lim[1]), (lim[2], lim[3]), target_hue=hue)

        # chart4's chosen line is itself red, so draw the extraction in magenta there.
        line_bgr = (255, 0, 255) if name == "chart4" else (0, 0, 255)
        calib = "ticks" if args.ticks else "box edges"
        label = f"box={box_mode} colour={hex_color} line={mode} calib={calib} px x {px['px_x'].min():.0f}-{px['px_x'].max():.0f}"
        overlay = draw(cv2.imread(str(path)), px, box, label, line_bgr, TICKS[name] if args.ticks else None)
        suffix = "_ticks_overlay" if args.ticks else "_overlay"
        cv2.imwrite(str(OUT_DIR / f"{name}{suffix}.png"), overlay)

        i, j = df["y"].idxmax(), df["y"].idxmin()
        print(
            f"{name}: box {box_mode} {box}, colour {hex_color}, line {mode}, {calib}; "
            f"first ({df.x.iloc[0]:.3f}, {df.y.iloc[0]:.3f}) last ({df.x.iloc[-1]:.3f}, {df.y.iloc[-1]:.3f}) "
            f"max ({df.x[i]:.3f}, {df.y[i]:.3f}) min ({df.x[j]:.3f}, {df.y[j]:.3f})"
        )


if __name__ == "__main__":
    main()
