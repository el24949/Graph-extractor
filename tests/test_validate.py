"""Tests for the rolling validation in src/validate.py."""

import numpy as np
import pytest

from src.forecast import forecast_ets, forecast_naive
from src.validate import rolling_validation

H = 10

# A silent fallback to naive would make ETS look like naive, so fail on it.
pytestmark = pytest.mark.filterwarnings("error:.*using naive forecast")


def test_linear_series_shape_and_errors():
    y = np.arange(100, dtype=float)

    naive_err = rolling_validation(y, forecast_naive, h=H)
    ets_err = rolling_validation(y, forecast_ets, h=H)

    # Cut points t = 30, 32, ..., 90 -> 31 windows.
    assert naive_err.ndim == 2 and naive_err.shape[1] == H
    assert naive_err.shape == ets_err.shape == (31, H)
    assert naive_err.mean() > 0  # naive misses the trend
    assert ets_err.mean() < 1.0  # Holt's trend fits a straight line almost exactly


def test_constant_series_raises():
    with pytest.raises(ValueError):
        rolling_validation(np.full(100, 5.0), forecast_naive, h=H)


def test_naive_error_grows_with_horizon():
    y = 10 + 0.5 * np.arange(100, dtype=float)
    by_horizon = rolling_validation(y, forecast_naive, h=H).mean(axis=0)
    assert by_horizon[0] < by_horizon[-1]
