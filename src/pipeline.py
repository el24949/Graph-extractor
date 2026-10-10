"""Extract a time series from a line chart image.

Runs plot-area detection, line isolation and (optionally) calibration.
Uses the image alone: nothing here reads the *_meta.json ground truth.

CLI, from the project root:
    python -m src.pipeline image.png --list-colors
    python -m src.pipeline image.png --color 1 --xmin 0 --xmax 99 --ymin 40 --ymax 60 --out out.csv
Leave out the axis limits to get pixel coordinates instead. Leave out --color
to use all coloured pixels (or the dark fallback for a black line).
"""

import argparse

import cv2
import pandas as pd

from src.calibrate import calibrate
from src.extract import extract_line_pixels, find_plot_area, find_series_colors


def _read_image(img_path):
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")
    return img


def series_colors(img_path):
    """Find the plot area and the line colours in it.

    Returns (box, box_mode, colors), where colors is the list from
    find_series_colors (largest first; each has "hue", "count", "hex").
    Pass a chosen colour's "hue" to extract_series as target_hue.
    """
    img = _read_image(img_path)
    box, box_mode = find_plot_area(img)
    return box, box_mode, find_series_colors(img, box)


def extract_series(img_path, x_ref=None, y_ref=None, target_hue=None):
    """Extract the line from the chart at img_path.

    x_ref = (xmin, xmax) and y_ref = (ymin, ymax) are the axis values at the
    edges of the plot area. They are paired with the detected box edges
    (left/right, bottom/top) to calibrate. If both are given, the DataFrame has
    columns x, y; if neither is given, it has pixel columns px_x, px_y.

    target_hue (OpenCV hue 0-179, e.g. a colour from series_colors) extracts
    only the line of that colour. Without it, all coloured pixels are used.

    Returns (df, mode, box, box_mode): mode is the line mask used ("color" or
    "dark"), box is the detected (left, top, right, bottom) pixel box, and
    box_mode says how the box was found ("axes" or "grid").
    """
    if (x_ref is None) != (y_ref is None):
        raise ValueError("Give both x_ref and y_ref, or neither")

    img = _read_image(img_path)
    box, box_mode = find_plot_area(img)
    px_x, px_y, mode = extract_line_pixels(img, box, target_hue=target_hue)

    if x_ref is None:
        return pd.DataFrame({"px_x": px_x, "px_y": px_y}), mode, box, box_mode

    # Pair each axis value with the matching detected edge. The y refs go
    # bottom -> ymin and top -> ymax, which flips the image's downward y axis.
    left, top, right, bottom = box
    x_vals, y_vals = calibrate(
        px_x,
        px_y,
        x_ref=((left, x_ref[0]), (right, x_ref[1])),
        y_ref=((bottom, y_ref[0]), (top, y_ref[1])),
    )
    return pd.DataFrame({"x": x_vals, "y": y_vals}), mode, box, box_mode


def main():
    """Command-line entry point: extract one chart and save it as CSV."""
    parser = argparse.ArgumentParser(description="Extract a time series from a line chart image.")
    parser.add_argument("image", help="path to the chart image")
    parser.add_argument("--xmin", type=float, help="x value at the left edge of the plot area")
    parser.add_argument("--xmax", type=float, help="x value at the right edge of the plot area")
    parser.add_argument("--ymin", type=float, help="y value at the bottom edge of the plot area")
    parser.add_argument("--ymax", type=float, help="y value at the top edge of the plot area")
    parser.add_argument("--out", help="output CSV path")
    parser.add_argument("--list-colors", action="store_true", help="list the line colours found and exit")
    parser.add_argument("--color", type=int, help="extract only colour N from --list-colors (1 = largest)")
    args = parser.parse_args()

    try:
        box, box_mode, colors = series_colors(args.image)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Plot area from {box_mode}, box={box}. Line colours:")
    for i, c in enumerate(colors, 1):
        print(f"  {i}: {c['hex']}  hue={c['hue']:.0f}  {c['count']} px")
    if not colors:
        print("  (none: no coloured pixels, the dark fallback will be used)")
    if args.list_colors:
        return
    if args.out is None:
        parser.error("--out is required unless --list-colors is given")

    target_hue = None
    if args.color is not None:
        if not 1 <= args.color <= len(colors):
            parser.error(f"--color must be between 1 and {len(colors)}")
        target_hue = colors[args.color - 1]["hue"]

    limits = [args.xmin, args.xmax, args.ymin, args.ymax]
    if all(v is None for v in limits):
        x_ref = y_ref = None
    elif all(v is not None for v in limits):
        x_ref, y_ref = (args.xmin, args.xmax), (args.ymin, args.ymax)
    else:
        parser.error("give all four of --xmin --xmax --ymin --ymax, or none for pixel output")

    try:
        df, mode, box, box_mode = extract_series(args.image, x_ref, y_ref, target_hue)
    except ValueError as exc:
        parser.exit(1, f"Error: {exc}\n")
    df.to_csv(args.out, index=False)
    print(f"Saved {len(df)} points to {args.out} (line mode={mode}, plot area from {box_mode}, box={box})")


if __name__ == "__main__":
    main()
