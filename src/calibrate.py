import numpy as np


def pixel_to_value(p, p1, v1, p2, v2):
    """Linearly map pixel coordinate(s) p to data value(s), given two
    reference points (p1 -> v1) and (p2 -> v2)."""
    if p1 == p2:
        raise ValueError("Reference pixels must be different")
    p = np.asarray(p, dtype=float)
    return v1 + (p - p1) * (v2 - v1) / (p2 - p1)


def calibrate(px_x, px_y, x_ref, y_ref):
    """Convert pixel arrays to data values.

    x_ref = ((px1, val1), (px2, val2)) e.g. ((left, xmin), (right, xmax))
    y_ref = ((py1, val1), (py2, val2)) e.g. ((bottom, ymin), (top, ymax))
    Returns (x_values, y_values).
    """
    (xp1, xv1), (xp2, xv2) = x_ref
    (yp1, yv1), (yp2, yv2) = y_ref
    x_values = pixel_to_value(px_x, xp1, xv1, xp2, xv2)
    y_values = pixel_to_value(px_y, yp1, yv1, yp2, yv2)
    return x_values, y_values
