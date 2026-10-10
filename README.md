# Time Series Graph Extraction & Forecast Risk Tool

Upload an image of a line chart. The tool extracts the plotted data with
computer vision, forecasts the next points, and estimates **how likely each
forecasted point is to be wrong**, using rolling forecast validation on the
extracted history.

> Status: extraction, calibration, forecasting, rolling validation, risk
> estimation and the Streamlit UI are implemented. Demo video: [in progress].

## 1. Problem

A chart image contains data, but not in a usable form. We want to
(1) recover the numbers from the pixels, (2) forecast forward, and
(3) say how much to trust that forecast, with a number instead of a guess.

## 2. Approach (how I thought about it)

The problem splits into three stages, and each one can fail independently,
so I built and measured them separately:

1. **Image -> data.** Classical CV (no deep learning): find the axes, isolate
   the line, convert pixels to values. Classical methods are transparent,
   fast, and easy to debug.
2. **Data -> forecast.** Three simple models (naive, ETS, ARIMA) behind one
   interface. The point is the validation, not model sophistication.
3. **Forecast -> risk.** Instead of assuming a model is good, I test it on
   the past: pretend we are at time *t*, forecast, compare with what really
   happened, and repeat. The share of past forecasts that missed by more than
   a tolerance is the estimated probability of being wrong.

**Ground truth first.** I generate synthetic charts from known data, so every
stage can be scored against the true answer. Extraction code never reads the
answer key (`*_meta.json`); only the evaluation script does.

## 3. Pipeline

```
image -> detect plot area -> isolate line -> pixels -> calibrate -> series
      -> resample (100 pts) -> rolling validation -> P(wrong) + CI -> forecast
```

### 3.1 Plot-area detection (`src/extract.py`)
Grayscale -> threshold dark pixels -> morphological opening with long thin
horizontal/vertical kernels. Text and the data line are too short to survive;
the axes survive. Their extent gives the plot box.

### 3.2 Line isolation (`src/extract.py`)
Crop inside the box (3 px inset to drop the axis lines). Keep **colored**
pixels via HSV saturation (grid and axes are gray). **Fallback:** if there are
too few colored pixels (black/gray lines), use dark pixels (grayscale < 80).
For each x column take the median y of mask pixels; interpolate empty columns.

### 3.3 Calibration (`src/calibrate.py`)
Linear map from pixels to values using two reference points per axis:

```
value = v1 + (p - p1) * (v2 - v1) / (p2 - p1)
```

The image y-axis is flipped; passing (bottom, ymin) and (top, ymax) makes
`p2 - p1` negative, so no special case is needed.

### 3.4 Forecasting (`src/forecast.py`)
The extracted series has one point per pixel column (hundreds), so it is
**resampled to 100 evenly spaced points**, which the models assume.
Models: **naive** (last value), **ETS** (Holt, additive trend, no seasonality),
**ARIMA(1,1,1)**. No seasonality, since the period is unknown from an image.
If a statsmodels fit fails or returns NaN, it falls back to naive and warns.

### 3.5 Rolling validation (`src/validate.py`)
Expanding window: for each cut point *t* (from `min_train=30`, every
`step=2`), fit on `y[:t]`, forecast `h=10` points, compare with the real
`y[t:t+h]`. Error = `|pred - actual| / training_range * 100`, so it is a
percentage of the chart's scale and comparable across charts. The full error
matrix `(windows, h)` is kept, not just the mean.

### 3.6 Probability of being wrong (`src/risk.py`)
- A forecasted point is **wrong** if its error exceeds a user-set tolerance
  (default 10% of the range).
- **P(wrong)** = fraction of validation errors above the tolerance, computed
  **per forecast step**, because 1 step ahead is much easier than 10.
- **95% confidence intervals**, two kinds:
  - **Per step: Wilson score interval.** Each step's P(wrong) is a count of
    misses out of the windows, so Wilson gives a sensible interval even when
    there are 0 misses (a bootstrap would collapse to [0, 0] there).
  - **Overall: bootstrap over windows** (2000 resamples of whole windows,
    fixed seed), since the overall rate pools all steps of a window together.
- The model with the lowest rolling error is chosen per chart.

## 4. Results

### 4.1 Extraction accuracy (synthetic charts, 15 samples)
Errors relative to the y-range. Axis limits come from the meta files, **not**
from reading tick labels.

| chart | mode | RMSE% | MAE% |
|---|---|---:|---:|
| chart_01 | color | 4.87 | 3.70 |
| chart_02 | color | 2.32 | 1.82 |
| chart_03 | color | 1.03 | 0.79 |
| chart_04 | color | 0.76 | 0.60 |
| chart_05 | color | 0.77 | 0.60 |
| chart_06 | dark | 1.70 | 1.33 |
| chart_07 | color | 1.81 | 1.39 |
| chart_08 | color | 0.51 | 0.41 |
| chart_09 | color | 2.03 | 1.47 |
| chart_10 | color | 2.56 | 2.03 |
| chart_11 | color | 1.75 | 1.38 |
| chart_12 | color | 1.17 | 0.93 |
| chart_13 | color | 1.42 | 1.05 |
| chart_14 | dark | 1.71 | 1.28 |
| chart_15 | color | 1.73 | 1.38 |
| **mean** | | **1.74** | **1.34** |
| **max** | | **4.87** | **3.70** |

Mean RMSE 1.74%, max 4.87% (chart_01, sharp spikes are flattened by the
per-column median). Overlay example: `docs/overlays/chart_01_overlay.png`.

**These results are on clean synthetic charts. Real images will be worse.**

### 4.2 Rolling validation example (chart_04, trend + seasonal)
Mean error %: naive 16.8, ETS 25.7, ARIMA 18.6. ETS/ARIMA win for the first
3-4 steps, then lose to naive because the chart has a seasonal wave neither
model captures. One chart with overlapping windows is an example, not a
model ranking.

### 4.3 Risk output
chart_04, tolerance 10% of the range. Chosen model: **naive**.
Overall P(wrong) 0.61, 95% CI [0.53, 0.68] (bootstrap).

| step | P(wrong) | 95% CI (Wilson) |
|---:|---:|---|
| 1 | 0.00 | [0.00, 0.11] |
| 2 | 0.39 | [0.24, 0.56] |
| 3 | 0.45 | [0.29, 0.62] |
| 4 | 0.71 | [0.53, 0.84] |
| 5 | 0.71 | [0.53, 0.84] |
| 6 | 0.77 | [0.60, 0.89] |
| 7 | 0.74 | [0.57, 0.86] |
| 8 | 0.77 | [0.60, 0.89] |
| 9 | 0.71 | [0.53, 0.84] |
| 10 | 0.81 | [0.64, 0.91] |

At step 1 no misses were seen in 31 windows, so P(wrong) is 0, but the Wilson
interval still allows up to 11%. Zero observed misses does not mean zero risk.

Risk climbs from 0% at step 1 to about 80% at step 10 for this chart.

## 5. Assumptions and limitations

- **Axis values are supplied, not read.** OCR of tick labels is not
  implemented; the user (or tests) provides two reference values per axis.
- Single line, line chart, mostly white background, numeric x-axis.
- Test charts hide the top/right border, so plot-area detection is easier
  than on real charts with a full box.
- Black/gray lines depend on the dark-pixel fallback; dark text or markers
  inside the plot area can confuse it.
- Per-column median flattens sharp spikes.
- ARIMA(1,1,1) has no drift; on long horizons it may flatten.
- No seasonality modeling.
- **Rolling windows overlap** (`step=2 < h=10`), so they are not independent.
  Both intervals assume they are: the per-step Wilson interval treats each
  window as an independent trial, and the overall bootstrap resamples windows
  as if independent. Both are therefore too narrow (optimistic).
- The best model is selected on the same errors used to estimate P(wrong),
  which makes the estimate slightly optimistic.
- P(wrong) is an **empirical estimate**, not an exact probability. It
  assumes the future behaves like the past.

## 6. Install and usage

### Install

Requires Python 3.13 (what the project was built and tested on).

```
python -m venv .venv
.venv\Scripts\activate          # Windows (cmd); PowerShell: .venv\Scripts\Activate.ps1
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

Tick-label reading (OCR) is not implemented, so no OCR library is installed.
Axis values are entered by hand.

### Web app

```
streamlit run app.py
```

Then open the URL it prints (usually http://localhost:8501).

1. Upload a line chart (PNG or JPG) in the sidebar.
2. Enter the axis values at the edges of the plot area: `xmin`, `xmax`,
   `ymin`, `ymax`. These are not read from the image.
3. Set the tolerance (what counts as "wrong", as % of the range) and the
   forecast horizon `h`.

The page shows the original chart next to the extracted line in red, the mask
mode (`color` or `dark`), the chosen model, the overall P(wrong) with its 95%
CI, a chart of the series with the forecast, and a table of P(wrong) with CI
for each forecast step. A button downloads the extracted series as CSV.
Problems (no axes found, no line found, series too flat) are shown as error
messages.

To try it on a sample, upload `samples/chart_04.png` with x from `0` to `299`
and y from `-33.77` to `62.76` (the values in `chart_04_meta.json`).

### Command line

Extract one chart to CSV:

```
python -m src.pipeline samples/chart_04.png --xmin 0 --xmax 299 --ymin -33.77 --ymax 62.76 --out out.csv
```

Leave out all four limits to get pixel coordinates instead.

Other commands:

- `python -m src.generate_samples`: regenerate the synthetic charts
- `python -m src.evaluate`: extraction accuracy table, saved to `docs/extraction_results.md`
- `python -m src.overlay`: overlay images, saved to `docs/overlays/`
- `pytest`: run the tests

## 7. Repository layout

```
app.py      Streamlit web app
src/        extract, calibrate, pipeline, forecast, validate, risk, evaluate, overlay
tests/      pytest suites
samples/    synthetic charts + truth CSV + meta JSON
docs/       results table, overlays
```

## 8. Development process

Built with Claude Code as an assistant. I designed the pipeline and the
validation approach, set the evaluation rules (extraction never reads the
answer key; fallbacks must fail tests rather than hide bugs), reviewed the
results, and documented the limitations.
