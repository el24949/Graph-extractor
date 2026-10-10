"""Extract a time series from a line chart image.

Runs plot-area detection, line isolation and (optionally) calibration.
Uses the image alone: nothing here reads the *_meta.json ground truth.

CLI, from the project root:
    python -m src.pipeline image.png --xmin 0 --xmax 99 --ymin 40 --ymax 60 --out out.csv
Leave out the axis limits to get pixel coordinates instead.
"""

import argparse

import cv2
import pandas as pd

from src.calibrate import calibrate
from src.extract import detect_plot_area, extract_line_pixels


def extract_series(img_path, x_ref=None, y_ref=None):
    """Extract the line from the chart at img_path.

    x_ref = (xmin, xmax) and y_ref = (ymin, ymax) are the axis values at the
    edges of the plot area. They are paired with the detected box edges
    (left/right, bottom/top) to calibrate. If both are given, the DataFrame has
    columns x, y; if neither is given, it has pixel columns px_x, px_y.

    Returns (df, mode, box), where mode is "color" or "dark" and box is the
    detected (left, top, right, bottom) pixel box.
    """
    if (x_ref is None) != (y_ref is None):
        raise ValueError("Give both x_ref and y_ref, or neither")

    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")

    box = detect_plot_area(img)
    px_x, px_y, mode = extract_line_pixels(img, box)

    if x_ref is None:
        return pd.DataFrame({"px_x": px_x, "px_y": px_y}), mode, box

    # Pair each axis value with the matching detected edge. The y refs go
    # bottom -> ymin and top -> ymax, which flips the image's downward y axis.
    left, top, right, bottom = box
    x_vals, y_vals = calibrate(
        px_x,
        px_y,
        x_ref=((left, x_ref[0]), (right, x_ref[1])),
        y_ref=((bottom, y_ref[0]), (top, y_ref[1])),
    )
    return pd.DataFrame({"x": x_vals, "y": y_vals}), mode, box


def main():
    """Command-line entry point: extract one chart and save it as CSV."""
    parser = argparse.ArgumentParser(description="Extract a time series from a line chart image.")
    parser.add_argument("image", help="path to the chart image")
    parser.add_argument("--xmin", type=float, help="x value at the left edge of the plot area")
    parser.add_argument("--xmax", type=float, help="x value at the right edge of the plot area")
    parser.add_argument("--ymin", type=float, help="y value at the bottom edge of the plot area")
    parser.add_argument("--ymax", type=float, help="y value at the top edge of the plot area")
    parser.add_argument("--out", required=True, help="output CSV path")
    args = parser.parse_args()

    limits = [args.xmin, args.xmax, args.ymin, args.ymax]
    if all(v is None for v in limits):
        x_ref = y_ref = None
    elif all(v is not None for v in limits):
        x_ref, y_ref = (args.xmin, args.xmax), (args.ymin, args.ymax)
    else:
        parser.error("give all four of --xmin --xmax --ymin --ymax, or none for pixel output")

    df, mode, box = extract_series(args.image, x_ref, y_ref)
    df.to_csv(args.out, index=False)
    print(f"Saved {len(df)} points to {args.out} (mode={mode}, box={box})")


if __name__ == "__main__":
    main()
