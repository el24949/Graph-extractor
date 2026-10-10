"""Locate the plot area of a line chart image and extract the line's pixels.

Works from the image alone: nothing here reads the *_meta.json ground truth.
"""

import cv2
import numpy as np

# All sizes are fractions of the image, not pixels, so they scale with it.
# None of these is tuned to a particular image.

# Line candidates starting within this fraction of an image edge are ignored:
# they are screenshot borders, frames or window chrome, not chart axes.
BORDER_FRAC = 0.02
# A line must be at least this fraction of the image width/height to count.
MIN_LINE_FRAC = 1 / 3
# A line band may be at most this thick (fraction of the image, at least 3 px).
# Axes and gridlines are thin; filled areas and solid blocks are not.
MAX_THICKNESS_FRAC = 0.01
# A line is "strong" if it is at least this fraction as long as the longest one.
STRONG_FRAC = 0.5

# Adaptive darkness for axis lines. Thresholds are set relative to the
# background (median gray) and tried from strict to loose: background - 127
# (128 on white, the old fixed threshold), then - 95, then - 63. The first one
# that gives a valid box wins.
#
# Why a ladder and not Otsu: Otsu picks one cut from the whole histogram. On a
# mostly white chart it lands somewhere between the background and "everything
# else", so it also pulls in light gridlines, filled areas and anti-aliasing,
# and it moves the threshold on charts that already worked. The ladder keeps
# the strict result whenever it succeeds (so clean charts behave exactly as
# before) and only loosens when nothing valid is found, e.g. for mid-gray axes.
AXIS_CONTRASTS = (127, 95, 63)
# Gridline fallback: anything at least this much darker than the background
# counts as ink, so light gray gridlines (e.g. #dddddd on white) are included.
GRID_CONTRAST = 12

# Box sanity limits, as fractions of the image.
MIN_BOX_FRAC = 0.10  # each side at least 10% of the image width/height
MAX_BOX_AREA_FRAC = 0.90  # box at most 90% of the image area


def _open_lines(ink, width, height):
    """Keep only long straight horizontal and vertical runs of ink pixels."""
    h_len = max(int(width * MIN_LINE_FRAC), 10)
    v_len = max(int(height * MIN_LINE_FRAC), 10)
    h_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    v_lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    return h_lines > 0, v_lines > 0


def _line_bands(counts):
    """Group consecutive rows (or columns) that contain line pixels into bands.

    Returns (start, end, peak) per band, keeping only bands that are thin and
    not touching the image border, and of those only the strong ones. peak is
    the row/column with the most line pixels in the band.
    """
    n = len(counts)
    border = int(np.ceil(n * BORDER_FRAC))
    max_thickness = max(3, int(round(n * MAX_THICKNESS_FRAC)))

    bands = []
    i = 0
    while i < n:
        if counts[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and counts[j + 1] > 0:
            j += 1
        touches_border = i < border or j >= n - border
        if not touches_border and j - i + 1 <= max_thickness:
            bands.append((i, j, i + int(np.argmax(counts[i : j + 1]))))
        i = j + 1

    if not bands:
        return []
    longest = max(counts[peak] for _, _, peak in bands)
    return [b for b in bands if counts[b[2]] >= STRONG_FRAC * longest]


def _box_problem(box, shape):
    """Return why box is not a plausible plot area, or None if it is."""
    left, top, right, bottom = box
    height, width = shape[:2]
    if bottom <= top:
        return f"bottom ({bottom}) is not below top ({top})"
    if left >= right:
        return f"left ({left}) is not left of right ({right})"
    if right - left < MIN_BOX_FRAC * width or bottom - top < MIN_BOX_FRAC * height:
        return f"box {box} is too small for a {width}x{height} image"
    if (right - left) * (bottom - top) > MAX_BOX_AREA_FRAC * width * height:
        return f"box {box} covers almost the whole {width}x{height} image"
    return None


def validate_box(box, shape):
    """Raise ValueError if box is not a plausible plot area for an image of this shape."""
    problem = _box_problem(box, shape)
    if problem:
        raise ValueError(f"Invalid plot area: {problem}")


def _axes_box(gray, threshold):
    """Box from dark axis lines: the lowest long horizontal line is the x axis,
    the leftmost long vertical line is the y axis. Returns (box, reason)."""
    height, width = gray.shape
    ink = (gray < threshold).astype(np.uint8) * 255
    h_lines, v_lines = _open_lines(ink, width, height)
    h_bands = _line_bands(h_lines.sum(axis=1))
    v_bands = _line_bands(v_lines.sum(axis=0))
    if not h_bands or not v_bands:
        return None, f"no long horizontal and vertical lines darker than {threshold:.0f}"

    # Lowest strong horizontal line = x axis; leftmost strong vertical = y axis.
    # Choosing by position (not just length) skips a top frame line, a zero
    # line or dark gridlines when the chart has them.
    b_start, b_end, bottom = h_bands[-1]
    l_start, l_end, left = v_bands[0]

    # The axes span the plot area, so their far ends give the other two edges.
    # This also works for a full box, where the ends meet the top/right lines.
    right = int(np.nonzero(h_lines[b_start : b_end + 1].any(axis=0))[0].max())
    top = int(np.nonzero(v_lines[:, l_start : l_end + 1].any(axis=1))[0].min())
    return (left, top, right, bottom), None


def _grid_box(gray, threshold):
    """Box from light gridlines when there are no axes: the outermost gridlines
    in each direction, or a single direction's extent. Returns (box, reason)."""
    height, width = gray.shape
    ink = (gray < threshold).astype(np.uint8) * 255
    h_lines, v_lines = _open_lines(ink, width, height)
    h_bands = _line_bands(h_lines.sum(axis=1))
    v_bands = _line_bands(v_lines.sum(axis=0))

    def h_extent():
        rows = np.zeros(height, dtype=bool)
        for start, end, _ in h_bands:
            rows[start : end + 1] = True
        cols = np.nonzero(h_lines[rows].any(axis=0))[0]
        return int(cols.min()), int(cols.max())

    def v_extent():
        cols = np.zeros(width, dtype=bool)
        for start, end, _ in v_bands:
            cols[start : end + 1] = True
        rows = np.nonzero(v_lines[:, cols].any(axis=1))[0]
        return int(rows.min()), int(rows.max())

    # Top/bottom from the outermost horizontal gridlines if there are at least
    # two; otherwise from how far the vertical gridlines reach. Same for sides.
    if len(h_bands) >= 2:
        top, bottom = h_bands[0][2], h_bands[-1][2]
    elif v_bands:
        top, bottom = v_extent()
    else:
        return None, "no gridlines found"
    if len(v_bands) >= 2:
        left, right = v_bands[0][2], v_bands[-1][2]
    elif h_bands:
        left, right = h_extent()
    else:
        return None, "no gridlines found"
    return (left, top, right, bottom), None


def find_plot_area(img_bgr):
    """Return ((left, top, right, bottom), mode) for the chart's plot area.

    mode is "axes" when the box comes from the axis lines, or "grid" when no
    axes were found and the box comes from the gridlines instead. Raises
    ValueError if neither gives a plausible box.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    background = float(np.median(gray))

    # 1. Axis lines, from the strictest darkness threshold to the loosest.
    axes_reason = None
    for contrast in AXIS_CONTRASTS:
        box, reason = _axes_box(gray, background - contrast)
        if box is not None:
            reason = _box_problem(box, gray.shape)
            if reason is None:
                return box, "axes"
        axes_reason = reason

    # 2. No usable axes: fall back to light gridlines.
    box, grid_reason = _grid_box(gray, background - GRID_CONTRAST)
    if box is not None:
        grid_reason = _box_problem(box, gray.shape)
        if grid_reason is None:
            return box, "grid"

    raise ValueError(f"No plot area found. Axes: {axes_reason}. Gridlines: {grid_reason}.")


def detect_plot_area(img_bgr):
    """Return the (left, top, right, bottom) pixel box of the chart's plot area.

    Same as find_plot_area, without the mode.
    """
    return find_plot_area(img_bgr)[0]


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
