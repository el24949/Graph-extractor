import numpy as np

from src.validate import compare_models


def p_wrong(errors, tol_pct):
    """Overall fraction of validation errors above the tolerance."""
    return float((errors > tol_pct).mean())


def p_wrong_by_horizon(errors, tol_pct):
    """P(wrong) for each step ahead (one value per column)."""
    return (errors > tol_pct).mean(axis=0)


def bootstrap_ci(errors, tol_pct, axis=None, n_boot=2000, alpha=0.05, seed=0):
    """Confidence interval for P(wrong), resampling whole windows (rows).
    axis=None -> overall; axis=0 -> one interval per horizon."""
    rng = np.random.default_rng(seed)       # fixed seed = reproducible
    exceed = errors > tol_pct
    n = exceed.shape[0]
    stats = [exceed[rng.integers(0, n, n)].mean(axis=axis) for _ in range(n_boot)]
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)], axis=0)
    return lo, hi


def forecast_with_risk(y, models, tol_pct=10.0, h=10, min_train=30, step=2):
    """Pick the model with the lowest rolling error, forecast h points past
    the end of y, and attach P(wrong) with a 95% CI to each future point."""
    all_errors = compare_models(y, h, min_train, step)
    best = min(all_errors, key=lambda name: all_errors[name].mean())
    errors = all_errors[best]
    lo, hi = bootstrap_ci(errors, tol_pct, axis=0)
    return {
        "model": best,
        "forecast": models[best](np.asarray(y, dtype=float), h),
        "p_wrong": p_wrong_by_horizon(errors, tol_pct),
        "ci_low": lo,
        "ci_high": hi,
        "p_wrong_overall": p_wrong(errors, tol_pct),
        "overall_ci": bootstrap_ci(errors, tol_pct),
    }
