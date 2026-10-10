"""Basic sanity checks for src/forecast.py."""

import numpy as np
import pytest

import src.forecast as forecast
from src.forecast import MODELS, resample_series

H = 10

# A silent fallback to naive would hide a broken model, so treat it as a failure
# everywhere except the test that checks the fallback on purpose.
pytestmark = pytest.mark.filterwarnings("error:.*using naive forecast")


def linear_series(n=60, slope=0.5, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    return 10 + slope * np.arange(n) + rng.normal(0, noise, n)


@pytest.mark.parametrize("name", MODELS)
def test_returns_h_finite_values(name):
    pred = MODELS[name](linear_series(), H)
    assert isinstance(pred, np.ndarray)
    assert pred.shape == (H,)
    assert not np.isnan(pred).any()


@pytest.mark.parametrize("name", ["ets", "arima"])
def test_rising_input_gives_rising_forecast(name):
    y = linear_series(noise=0.2)
    pred = MODELS[name](y, H)
    assert pred[-1] > pred[0], f"{name} forecast is not rising: {pred}"
    assert pred[-1] > y[-1], f"{name} forecast ends below the last observed value"


def test_resample_series():
    x = np.array([0.0, 1.0, 3.0, 4.0])
    y = np.array([0.0, 2.0, 6.0, 8.0])
    x_new, y_new = resample_series(x, y, n=5)
    np.testing.assert_allclose(x_new, [0, 1, 2, 3, 4])
    np.testing.assert_allclose(y_new, [0, 2, 4, 6, 8])


@pytest.mark.filterwarnings("default")
def test_fallback_to_naive_when_fit_fails(monkeypatch):
    def broken_holt(*args, **kwargs):
        raise ValueError("simulated fit failure")

    monkeypatch.setattr(forecast, "Holt", broken_holt)
    y = linear_series()
    with pytest.warns(UserWarning, match="ets failed.*using naive forecast"):
        pred = forecast.forecast_ets(y, H)
    np.testing.assert_array_equal(pred, np.full(H, y[-1]))
