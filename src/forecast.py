"""Simple forecasting models for an extracted time series.

Every model has the same signature, forecast_<name>(y_train, h), and returns
a numpy array of h predictions. The statsmodels models fall back to the naive
forecast if fitting fails or produces a serious warning.
"""

import warnings

import numpy as np
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import Holt

# Warnings that mean the fitted model should not be trusted.
BAD_WARNINGS = (ConvergenceWarning, RuntimeWarning)


def resample_series(x, y, n=100):
    """Interpolate (x, y) onto n equally spaced x points; return x_new, y_new.

    The extracted series has one point per pixel column, so its length depends
    on the image width. Resampling gives every chart the same number of evenly
    spaced points, which the forecasting models assume.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(x)
    x_new = np.linspace(x[order[0]], x[order[-1]], n)
    y_new = np.interp(x_new, x[order], y[order])
    return x_new, y_new


def forecast_naive(y_train, h):
    """Repeat the last observed value h times."""
    return np.full(h, float(np.asarray(y_train)[-1]))


def _with_fallback(name, fit_and_forecast, y_train, h):
    """Run fit_and_forecast(y, h); fall back to naive on errors, bad warnings or non-finite output."""
    y = np.asarray(y_train, dtype=float)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pred = np.asarray(fit_and_forecast(y, h), dtype=float)
        bad = [w for w in caught if issubclass(w.category, BAD_WARNINGS)]
        if bad:
            raise RuntimeError(f"{bad[0].category.__name__}: {bad[0].message}")
        if pred.shape != (h,) or not np.all(np.isfinite(pred)):
            raise RuntimeError("forecast has the wrong length or contains NaN/inf")
    except Exception as exc:  # any statsmodels failure: keep the pipeline running
        warnings.warn(f"{name} failed ({exc}); using naive forecast instead", stacklevel=3)
        return forecast_naive(y, h)
    return pred


def forecast_ets(y_train, h):
    """Holt's linear method: exponential smoothing with additive trend, no seasonality."""
    return _with_fallback("ets", lambda y, h: Holt(y, initialization_method="estimated").fit().forecast(h), y_train, h)


def forecast_arima(y_train, h):
    """ARIMA(1,1,1) forecast."""
    return _with_fallback("arima", lambda y, h: ARIMA(y, order=(1, 1, 1)).fit().forecast(h), y_train, h)


MODELS = {
    "naive": forecast_naive,
    "ets": forecast_ets,
    "arima": forecast_arima,
}
