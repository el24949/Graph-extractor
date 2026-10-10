import numpy as np

from src.forecast import MODELS


def rolling_validation(y, model_fn, h=10, min_train=30, step=2):
    """Expanding-window rolling forecast validation.

    At each cut point t we pretend we only know y[:t], forecast the next h
    points, and compare them with the real y[t:t+h].
    Returns an array of shape (n_windows, h) with absolute errors expressed
    as a % of the training range (so charts with different scales compare).
    """
    y = np.asarray(y, dtype=float)
    if len(y) < min_train + h:
        raise ValueError("Series too short for this min_train and h")

    errors = []
    for t in range(min_train, len(y) - h + 1, step):
        train = y[:t]                 # only the past
        actual = y[t:t + h]           # the "future" we pretend not to know
        rng = train.max() - train.min()
        if rng == 0:                  # flat history: % error is undefined
            continue
        pred = model_fn(train, h)
        errors.append(np.abs(pred - actual) / rng * 100)

    if not errors:
        raise ValueError("No valid windows (series is flat?)")
    return np.array(errors)


def summarize(errors):
    """Baseline numbers from the error matrix."""
    return {
        "n_windows": errors.shape[0],
        "mae_pct": float(errors.mean()),                    # mean error baseline
        "mae_by_horizon": errors.mean(axis=0).tolist(),     # error grows with step ahead
        "p90_pct": float(np.percentile(errors, 90)),
    }


def compare_models(y, h=10, min_train=30, step=2):
    """Run rolling validation for every model in MODELS."""
    return {name: rolling_validation(y, fn, h, min_train, step)
            for name, fn in MODELS.items()}
