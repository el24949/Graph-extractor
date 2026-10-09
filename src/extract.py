"""Locate the plot area of a line chart image and extract the line's pixels.

Works from the image alone: nothing here reads the *_meta.json ground truth.
"""

import cv2
import numpy as np


def detect_plot_area(img_bgr):
    """Return the (left, top, right, bottom) pixel box of the chart's axes.

    Finds the long straight dark lines (the x and y axis lines) and uses
    their positions and extents as the box edges.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    # Dark pixels become 255: axis lines, tick labels, and dark data lines.
    # Light grid lines (~#dddddd) fall above the threshold and are dropped.
    _, dark = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)

    # Opening with a long, 1px-thick kernel keeps only straight runs at least
    # that long. Text, ticks and the wiggly data line are too short to survive.
    h_len = max(width // 3, 10)
    v_len = max(height // 3, 10)
    h_lines = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    v_lines = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))

    # The x axis is the row with the most surviving horizontal pixels;
    # the y axis is the column with the most surviving vertical pixels.
    h_counts = (h_lines > 0).sum(axis=1)
    v_counts = (v_lines > 0).sum(axis=0)
    if h_counts.max() == 0 or v_counts.max() == 0:
        raise ValueError("Could not find both axis lines")
    bottom = int(np.argmax(h_counts))
    left = int(np.argmax(v_counts))

    # The axis lines span the full plot area, so their far ends give the
    # remaining edges: where the x axis ends on the right, and where the
    # y axis ends at the top.
    right = int(np.nonzero(h_lines[bottom])[0].max())
    top = int(np.nonzero(v_lines[:, left])[0].min())

    return left, top, right, bottom


def extract_line_pixels(img_bgr, box, inset=3, sat_threshold=60, min_color_pixels=100, dark_threshold=80):
    """Return (px_x, px_y, mode): one line y-position per pixel column inside box.

    Coordinates are in full-image pixels. Columns where no line pixel was
    found are filled by linear interpolation from their neighbours.

    mode is "color" when the line was found by saturation, or "dark" when
    fewer than min_color_pixels coloured pixels were found and the mask was
    built from dark pixels (grayscale < dark_threshold) instead.
    """
    left, top, right, bottom = box

    # Crop inside the box, stepping in a few pixels so the axis lines and
    # tick marks are excluded.
    x0, y0 = left + inset, top + inset
    crop = img_bgr[y0 : bottom - inset, x0 : right - inset]

    # The data line is coloured; the background, grid, axes and text are
    # white, grey or black, which all have low saturation.
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = hsv[:, :, 1] > sat_threshold
    mode = "color"

    # A black or grey line has no saturation, so the colour mask comes back
    # (nearly) empty. Fall back to dark pixels; the light grid stays excluded.
    if mask.sum() < min_color_pixels:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        mask = gray < dark_threshold
        mode = "dark"

    # For each column, the median row of the line's pixels is its centre.
    n_cols = crop.shape[1]
    ys = np.full(n_cols, np.nan)
    for col in range(n_cols):
        rows = np.nonzero(mask[:, col])[0]
        if rows.size:
            ys[col] = np.median(rows)

    found = ~np.isnan(ys)
    if not found.any():
        raise ValueError("No line pixels found inside the plot area (tried colour and dark masks)")

    # Fill empty columns from the nearest found columns on either side.
    cols = np.arange(n_cols)
    ys[~found] = np.interp(cols[~found], cols[found], ys[found])

    # Shift from crop coordinates back to full-image coordinates.
    px_x = (cols + x0).astype(float)
    px_y = ys + y0
    return px_x, px_y, mode
