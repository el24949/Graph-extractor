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


# --- Line isolation -------------------------------------------------------

# Hues are in OpenCV units: 0-179, i.e. degrees / 2, and they wrap around.
# Two colours within this many units (20 degrees) count as the same series.
HUE_TOL = 10
# Ignore very dark pixels when reading colour: their hue is mostly noise.
MIN_VALUE = 50
# Drop colour clusters smaller than this share of the saturated pixels.
MIN_COLOR_FRAC = 0.01
# k-means is fitted on at most this many pixels (evenly spaced, deterministic).
MAX_KMEANS_PIXELS = 5000


def _crop_inside(img_bgr, box, inset):
    """Crop the plot area, stepping in `inset` px so axes and ticks are excluded.
    Returns (crop, x0, y0) where (x0, y0) is the crop's top-left in the image."""
    left, top, right, bottom = box
    x0, y0 = left + inset, top + inset
    return img_bgr[y0 : bottom - inset, x0 : right - inset], x0, y0


def _hue_distance(hue, target):
    """Circular distance between hues in OpenCV units (red at 0 and 179 are close)."""
    d = np.abs(np.asarray(hue, dtype=float) - target) % 180
    return np.minimum(d, 180 - d)


def _circular_mean_hue(hues, weights=None):
    angles = np.asarray(hues, dtype=float) * (2 * np.pi / 180)
    angle = np.arctan2(np.average(np.sin(angles), weights=weights), np.average(np.cos(angles), weights=weights))
    return float((angle * 180 / (2 * np.pi)) % 180)


def find_series_colors(img_bgr, box, k=4, inset=3, sat_threshold=60):
    """Return the dominant line colours inside the plot area, largest first.

    Runs k-means on the hue of saturated pixels, then merges clusters closer
    than HUE_TOL (k is an upper bound; one coloured line gives one colour) and
    drops tiny ones. Each entry is a dict with "hue" (OpenCV units, 0-179, to
    pass as target_hue), "count" (pixels), "bgr" and "hex" (a typical colour
    of the cluster, for showing a swatch). Returns [] if nothing is saturated,
    e.g. a black line, which extract_line_pixels handles with its dark mode.
    """
    from sklearn.cluster import KMeans  # imported here: only needed for colour lists

    crop, _, _ = _crop_inside(img_bgr, box, inset)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturated = (hsv[:, :, 1] > sat_threshold) & (hsv[:, :, 2] > MIN_VALUE)
    hues = hsv[:, :, 0][saturated].astype(float)
    bgrs = crop[saturated]
    if hues.size == 0:
        return []

    # Hue is an angle, so cluster points on the circle (cos, sin), not raw hue:
    # otherwise reds at 2 and 178 would land in different clusters.
    angles = hues * (2 * np.pi / 180)
    points = np.column_stack([np.cos(angles), np.sin(angles)])
    n_clusters = min(k, len(np.unique(hues)))
    sample = points[:: max(1, len(points) // MAX_KMEANS_PIXELS)]
    labels = KMeans(n_clusters=n_clusters, n_init=10, random_state=0).fit(sample).predict(points)

    clusters = [(hues[labels == c], bgrs[labels == c]) for c in range(n_clusters)]
    clusters = [(h, b) for h, b in clusters if h.size]
    clusters.sort(key=lambda hb: -hb[0].size)

    # Merge clusters of (nearly) the same hue: k-means splits one line into
    # several clusters when there are fewer colours than k.
    groups = []
    for h, b in clusters:
        hue = _circular_mean_hue(h)
        for g in groups:
            if _hue_distance(hue, g["hue"]) < HUE_TOL:
                g["hues"].append(h)
                g["bgrs"].append(b)
                g["hue"] = _circular_mean_hue(np.concatenate(g["hues"]))
                break
        else:
            groups.append({"hue": hue, "hues": [h], "bgrs": [b]})

    colors = []
    for g in groups:
        count = int(sum(h.size for h in g["hues"]))
        if count < MIN_COLOR_FRAC * hues.size:
            continue
        # The most saturated quarter of the pixels is the line's core colour;
        # the rest is anti-aliasing blended with the background.
        b = np.concatenate(g["bgrs"])
        sat = cv2.cvtColor(b.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV)[:, 0, 1]
        core = b[sat >= np.percentile(sat, 75)]
        blue, green, red = (int(v) for v in np.median(core, axis=0))
        colors.append(
            {"hue": g["hue"], "count": count, "bgr": (blue, green, red), "hex": f"#{red:02x}{green:02x}{blue:02x}"}
        )
    colors.sort(key=lambda c: -c["count"])
    return colors


def _column_runs(mask):
    """For each column, the vertical runs of mask pixels as (start_row, end_row)."""
    runs = []
    for col in range(mask.shape[1]):
        rows = np.flatnonzero(mask[:, col])
        if rows.size == 0:
            runs.append([])
            continue
        breaks = np.flatnonzero(np.diff(rows) > 1)
        starts = np.r_[rows[0], rows[breaks + 1]]
        ends = np.r_[rows[breaks], rows[-1]]
        runs.append(list(zip(starts.tolist(), ends.tolist())))
    return runs


def _closest_run(runs, y):
    """The run nearest to row y (distance 0 if y lies inside the run)."""
    return min(runs, key=lambda r: (max(r[0] - y, 0, y - r[1]), abs((r[0] + r[1]) / 2 - y)))


def _track_line(mask):
    """Follow one line through the mask, column by column.

    Starts inside the largest connected component (the main line, not a legend
    sample or stray marks), then walks right and left. In each column it picks
    the vertical run closest to the previous column's y and takes the run's
    median row. Returns an array of y per column, NaN where a column is empty.
    """
    n_rows, n_cols = mask.shape
    ys = np.full(n_cols, np.nan)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n_labels <= 1:
        return ys
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    in_biggest = labels == biggest

    # Start in the middle column of the largest component, on its run there.
    comp_cols = np.flatnonzero(in_biggest.any(axis=0))
    start = int(comp_cols[len(comp_cols) // 2])
    runs = _column_runs(mask)
    start_run = max(runs[start], key=lambda r: in_biggest[r[0] : r[1] + 1, start].sum())
    ys[start] = (start_run[0] + start_run[1]) / 2  # median of a contiguous run

    for direction in (1, -1):
        prev_y = ys[start]
        col = start + direction
        while 0 <= col < n_cols:
            if runs[col]:
                run = _closest_run(runs[col], prev_y)
                ys[col] = prev_y = (run[0] + run[1]) / 2
            col += direction
    return ys


def extract_line_pixels(
    img_bgr,
    box,
    inset=3,
    sat_threshold=60,
    min_color_pixels=100,
    dark_threshold=80,
    target_hue=None,
    hue_tol=HUE_TOL,
):
    """Return (px_x, px_y, mode): the line's y-position per pixel column.

    Coordinates are in full-image pixels. Only the x-range where the line was
    actually found is returned: gaps inside it are filled by linear
    interpolation, but nothing is extrapolated past either end.

    target_hue (OpenCV units, 0-179, e.g. from find_series_colors) keeps only
    pixels of that colour, within hue_tol. Without it, all saturated pixels
    are used, as before.

    mode is "color" when the line was found by saturation, or "dark" when no
    target_hue was given, fewer than min_color_pixels coloured pixels were
    found, and the mask was built from dark pixels (grayscale < dark_threshold).
    """
    crop, x0, y0 = _crop_inside(img_bgr, box, inset)

    # The data line is coloured; the background, grid, axes and text are
    # white, grey or black, which all have low saturation.
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = hsv[:, :, 1] > sat_threshold
    mode = "color"

    if target_hue is not None:
        # Keep only the chosen series' colour (dark pixels have unreliable hue).
        mask &= (hsv[:, :, 2] > MIN_VALUE) & (_hue_distance(hsv[:, :, 0], target_hue) <= hue_tol)
        if mask.sum() < min_color_pixels:
            raise ValueError(f"No line pixels of the chosen colour (hue {target_hue:.0f}) inside the plot area")
    elif mask.sum() < min_color_pixels:
        # A black or grey line has no saturation, so the colour mask comes back
        # (nearly) empty. Fall back to dark pixels; the light grid stays excluded.
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        mask = gray < dark_threshold
        mode = "dark"

    # Follow one line instead of taking the median of everything in a column,
    # so a second series, a legend sample or a logo does not pull it off.
    ys = _track_line(mask)

    found = np.flatnonzero(~np.isnan(ys))
    if found.size == 0:
        raise ValueError("No line pixels found inside the plot area (tried colour and dark masks)")

    # Interpolate only between the first and last columns with data.
    cols = np.arange(found[0], found[-1] + 1)
    ys = np.interp(cols, found, ys[found])

    # Shift from crop coordinates back to full-image coordinates.
    return (cols + x0).astype(float), ys + y0, mode
