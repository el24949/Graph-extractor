"""Extract a time series from a line chart image.

Runs plot-area detection, line isolation and (optionally) calibration.
Uses the image alone: nothing here reads the *_meta.json ground truth.

CLI, from the project root:
    python -m src.pipeline image.png --list-colors
    python -m src.pipeline image.png --color 1 --xmin 0 --xmax 99 --ymin 40 --ymax 60 --out out.csv
    python -m src.pipeline image.png --box 80 40 810 240 --out out.csv
    python -m src.pipeline image.png --xtick 103 1 --xtick 553 5 --ytick 410 1 --ytick 75 6 --out out.csv
Leave out the axis limits to get pixel coordinates instead. Give --xtick and
--ytick (twice each: pixel, value) instead of the limits to calibrate from two
labelled ticks per axis rather than the box edges. Leave out --color
to use all coloured pixels (or the dark fallback for a black line). Give --box
to set the plot area by hand when detection fails or is wrong.
"""

import argparse

import cv2
import numpy as np
import pandas as pd

from src.calibrate import calibrate
from src.extract import extract_line_pixels, find_plot_area, find_series_colors

# extract_line_pixels crops this many pixels inside the box, so a manual box
# must leave at least one pixel row/column after cropping.
INSET_PX = 3


def _read_image(img_path):
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")
    return img


def validate_manual_box(box, shape):
    """Check a user-given (left, top, right, bottom) box; return it as ints.

    Only checks that the box is usable: whole pixels, positive size, inside the
    image, and big enough for the inset crop. Unlike automatic detection it
    does not reject large boxes: a tightly cropped chart can fill the image.
    """
    if len(box) != 4:
        raise ValueError(f"Invalid manual box {box}: give four values, left top right bottom")
    try:
        left, top, right, bottom = (int(v) for v in box)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid manual box {box}: values must be whole pixel numbers") from None
    if any(int(v) != v for v in box):
        raise ValueError(f"Invalid manual box {box}: values must be whole pixel numbers")

    height, width = shape[:2]
    if right <= left:
        raise ValueError(f"Invalid manual box {box}: right ({right}) must be greater than left ({left})")
    if bottom <= top:
        raise ValueError(f"Invalid manual box {box}: bottom ({bottom}) must be greater than top ({top})")
    if left < 0 or top < 0 or right > width - 1 or bottom > height - 1:
        raise ValueError(
            f"Invalid manual box {box}: must lie inside the image "
            f"(0 <= left, right <= {width - 1}, 0 <= top, bottom <= {height - 1})"
        )
    if right - left <= 2 * INSET_PX or bottom - top <= 2 * INSET_PX:
        raise ValueError(f"Invalid manual box {box}: too small, each side must be more than {2 * INSET_PX} px")
    return left, top, right, bottom


def validate_ticks(ticks, axis):
    """Check two reference ticks ((p1, v1), (p2, v2)) for one axis; return them as floats.

    The pixels are full-image coordinates (x for the x axis, y for the y axis).
    The two pixels must differ (else there is no scale) and so must the values
    (else every point maps to the same value).
    """
    try:
        (p1, v1), (p2, v2) = ticks
        p1, v1, p2, v2 = (float(v) for v in (p1, v1, p2, v2))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {axis} ticks {ticks}: give two (pixel, value) pairs") from None
    if not np.all(np.isfinite([p1, v1, p2, v2])):
        raise ValueError(f"Invalid {axis} ticks {ticks}: pixels and values must be finite numbers")
    if p1 == p2:
        raise ValueError(f"Invalid {axis} ticks {ticks}: the two pixels must be different")
    if v1 == v2:
        raise ValueError(f"Invalid {axis} ticks {ticks}: the two values must be different")
    return (p1, v1), (p2, v2)


def _plot_area(img, box):
    """The detected box, or the validated manual one. Returns (box, box_mode)."""
    if box is None:
        return find_plot_area(img)
    return validate_manual_box(box, img.shape), "manual"


def series_colors(img_path, box=None):
    """Find the plot area and the line colours in it.

    box: optional manual (left, top, right, bottom); if given, detection is
    skipped and the box is only validated.

    Returns (box, box_mode, colors), where colors is the list from
    find_series_colors (largest first; each has "hue", "count", "hex").
    Pass a chosen colour's "hue" to extract_series as target_hue.
    """
    img = _read_image(img_path)
    box, box_mode = _plot_area(img, box)
    return box, box_mode, find_series_colors(img, box)


def extract_series(img_path, x_ref=None, y_ref=None, target_hue=None, box=None, x_ticks=None, y_ticks=None):
    """Extract the line from the chart at img_path.

    x_ref = (xmin, xmax) and y_ref = (ymin, ymax) are the axis values at the
    edges of the plot area. They are paired with the box edges (left/right,
    bottom/top) to calibrate. If both are given, the DataFrame has columns
    x, y; if neither is given, it has pixel columns px_x, px_y.

    target_hue (OpenCV hue 0-179, e.g. a colour from series_colors) extracts
    only the line of that colour. Without it, all coloured pixels are used.

    box: optional manual (left, top, right, bottom) in pixels. If given,
    plot-area detection is skipped; the box is validated (positive size,
    inside the image) and box_mode is "manual".

    x_ticks = ((px1, v1), (px2, v2)) and y_ticks = ((py1, v1), (py2, v2)) are
    an alternative to x_ref/y_ref: two labelled reference points per axis, as
    pixel positions in full-image coordinates with their values. They are
    passed straight to calibrate, so the box edges no longer need known
    values. Give both, and not together with x_ref/y_ref.

    Returns (df, mode, box, box_mode): mode is the line mask used ("color" or
    "dark"), box is the (left, top, right, bottom) pixel box used, and
    box_mode says where it came from ("axes", "grid" or "manual").
    """
    if (x_ref is None) != (y_ref is None):
        raise ValueError("Give both x_ref and y_ref, or neither")
    if (x_ticks is None) != (y_ticks is None):
        raise ValueError("Give both x_ticks and y_ticks, or neither")
    if x_ref is not None and x_ticks is not None:
        raise ValueError("Give either axis limits (x_ref, y_ref) or reference ticks (x_ticks, y_ticks), not both")
    if x_ticks is not None:
        x_ticks = validate_ticks(x_ticks, "x")
        y_ticks = validate_ticks(y_ticks, "y")

    img = _read_image(img_path)
    box, box_mode = _plot_area(img, box)
    px_x, px_y, mode = extract_line_pixels(img, box, target_hue=target_hue)

    if x_ticks is not None:
        x_vals, y_vals = calibrate(px_x, px_y, x_ref=x_ticks, y_ref=y_ticks)
        return pd.DataFrame({"x": x_vals, "y": y_vals}), mode, box, box_mode

    if x_ref is None:
        return pd.DataFrame({"px_x": px_x, "px_y": px_y}), mode, box, box_mode

    # Pair each axis value with the matching box edge. The y refs go
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
    parser.add_argument(
        "--box",
        type=int,
        nargs=4,
        metavar=("L", "T", "R", "B"),
        help="manual plot box in pixels (left top right bottom); skips plot-area detection",
    )
    parser.add_argument(
        "--xtick",
        type=float,
        nargs=2,
        action="append",
        metavar=("PX", "VAL"),
        help="x reference tick: pixel x (full image) and its value; give twice, instead of --xmin/--xmax",
    )
    parser.add_argument(
        "--ytick",
        type=float,
        nargs=2,
        action="append",
        metavar=("PY", "VAL"),
        help="y reference tick: pixel y (full image) and its value; give twice, instead of --ymin/--ymax",
    )
    args = parser.parse_args()

    try:
        box, box_mode, colors = series_colors(args.image, box=args.box)
    except (ValueError, FileNotFoundError) as exc:
        hint = "" if args.box else " (try --box L T R B to set the plot area by hand)"
        parser.exit(1, f"Error: {exc}{hint}\n")
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
    ticks = None
    if args.xtick is not None or args.ytick is not None:
        if any(v is not None for v in limits):
            parser.error("give either --xmin/--xmax/--ymin/--ymax or --xtick/--ytick, not both")
        if args.xtick is None or args.ytick is None or len(args.xtick) != 2 or len(args.ytick) != 2:
            parser.error("give --xtick PX VAL exactly twice and --ytick PY VAL exactly twice")
        ticks = (tuple(map(tuple, args.xtick)), tuple(map(tuple, args.ytick)))
        x_ref = y_ref = None
    elif all(v is None for v in limits):
        x_ref = y_ref = None
    elif all(v is not None for v in limits):
        x_ref, y_ref = (args.xmin, args.xmax), (args.ymin, args.ymax)
    else:
        parser.error("give all four of --xmin --xmax --ymin --ymax, or none for pixel output")

    try:
        df, mode, box, box_mode = extract_series(
            args.image, x_ref, y_ref, target_hue, box=args.box,
            x_ticks=ticks[0] if ticks else None, y_ticks=ticks[1] if ticks else None,
        )
    except ValueError as exc:
        parser.exit(1, f"Error: {exc}\n")
    df.to_csv(args.out, index=False)
    print(f"Saved {len(df)} points to {args.out} (line mode={mode}, plot area from {box_mode}, box={box})")


if __name__ == "__main__":
    main()
