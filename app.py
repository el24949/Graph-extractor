"""Streamlit UI: upload a line chart, extract the series, forecast it, and
show P(wrong) for each forecast step.

Run from the project root:
    streamlit run app.py
"""

import os
import tempfile
import warnings
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.forecast import MODELS, resample_series  # noqa: E402
from src.overlay import draw_overlay  # noqa: E402
from src.pipeline import extract_series  # noqa: E402
from src.risk import forecast_with_risk  # noqa: E402

N_RESAMPLE = 100


def analyze(img_path, x_ref, y_ref, tol_pct, h):
    """Run extraction, overlay, resampling and forecast_with_risk on one image.

    Returns a dict of everything the page shows. Raises ValueError with a
    readable message for the failures the page reports.
    """
    # Pixel run for the overlay, calibrated run for the data. src/ is left
    # unchanged, so this calls the pipeline twice rather than re-mapping.
    px_df, mode, box, box_mode = extract_series(img_path)
    df, *_ = extract_series(img_path, x_ref, y_ref)

    img = cv2.imread(str(img_path))
    overlay = draw_overlay(img, px_df["px_x"], px_df["px_y"], thickness=2)

    x, y = resample_series(df["x"], df["y"], n=N_RESAMPLE)

    # Collect fallback warnings so the page can show them instead of hiding them.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        risk = forecast_with_risk(y, MODELS, tol_pct=tol_pct, h=h)
    fallbacks = sorted({str(w.message) for w in caught if "using naive forecast" in str(w.message)})

    dx = x[1] - x[0]
    x_future = x[-1] + dx * np.arange(1, h + 1)

    return {
        "df": df,
        "mode": mode,
        "box_mode": box_mode,
        "box": box,
        "image_rgb": cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
        "overlay_rgb": cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB),
        "x": x,
        "y": y,
        "x_future": x_future,
        "risk": risk,
        "fallbacks": fallbacks,
    }


def forecast_figure(x, y, x_future, forecast, model):
    """Matplotlib figure of the resampled series and the forecast."""
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(x, y, color="#1f77b4", linewidth=1.5, label="extracted series (resampled)")
    ax.plot(
        np.r_[x[-1], x_future],
        np.r_[y[-1], forecast],
        color="#d62728",
        linewidth=1.5,
        linestyle="--",
        marker="o",
        markersize=3,
        label=f"forecast ({model})",
    )
    ax.axvline(x[-1], color="#999999", linewidth=0.8)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.grid(True, color="#eeeeee")
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


def risk_table(x_future, risk):
    """Per-step table of the forecast value and P(wrong) with its 95% CI."""
    return pd.DataFrame(
        {
            "step": np.arange(1, len(x_future) + 1),
            "x": x_future,
            "forecast": risk["forecast"],
            "P(wrong)": risk["p_wrong"],
            "CI low": risk["ci_low"],
            "CI high": risk["ci_high"],
        }
    )


def main():
    st.set_page_config(page_title="Graph Extractor", layout="wide")
    st.title("Time series graph extraction and forecast risk")

    with st.sidebar:
        uploaded = st.file_uploader("Chart image", type=["png", "jpg", "jpeg"])
        st.caption("Axis values at the edges of the plot area")
        xmin = st.number_input("xmin", value=0.0)
        xmax = st.number_input("xmax", value=100.0)
        ymin = st.number_input("ymin", value=0.0)
        ymax = st.number_input("ymax", value=100.0)
        tol_pct = st.slider("Tolerance (% of range)", min_value=1, max_value=30, value=10)
        h = st.slider("Forecast horizon h", min_value=5, max_value=20, value=10)

    if uploaded is None:
        st.info("Upload a line chart image in the sidebar to start.")
        return

    if xmin >= xmax or ymin >= ymax:
        st.error("Axis limits must satisfy xmin < xmax and ymin < ymax.")
        return

    # Save the upload to a temp file so the pipeline can read it by path.
    suffix = Path(uploaded.name).suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(uploaded.getvalue())
        tmp.close()
        result = analyze(tmp.name, (xmin, xmax), (ymin, ymax), tol_pct, h)
    except FileNotFoundError:
        st.error("Could not read the image. Is it a valid PNG or JPG?")
        return
    except ValueError as exc:
        msg = str(exc)
        if "No plot area found" in msg or "Invalid plot area" in msg:
            st.error(f"No plot area found: no usable axis lines or gridlines. Details: {msg}")
        elif "line pixels" in msg:
            st.error("No line found inside the plot area (no coloured or dark pixels).")
        elif "too short" in msg or "No valid windows" in msg:
            st.error(f"Series too short or flat for validation with h={h}: {msg}")
        else:
            st.error(f"Could not process this image: {msg}")
        return
    except Exception as exc:  # last resort: report, never crash the page
        st.error(f"Unexpected error: {type(exc).__name__}: {exc}")
        return
    finally:
        os.unlink(tmp.name)

    # --- Extraction ---
    st.subheader("Extraction")
    col1, col2 = st.columns(2)
    col1.image(result["image_rgb"], caption="Original", width="stretch")
    col2.image(result["overlay_rgb"], caption="Extracted line (red)", width="stretch")
    left, top, right, bottom = result["box"]
    st.write(
        f"Plot area from: **{result['box_mode']}**; line mask mode: **{result['mode']}**; "
        f"plot box (left, top, right, bottom): "
        f"({left}, {top}, {right}, {bottom}); {len(result['df'])} points extracted"
    )
    st.download_button(
        "Download extracted series (CSV)",
        data=result["df"].to_csv(index=False).encode("utf-8"),
        file_name=f"{Path(uploaded.name).stem}_extracted.csv",
        mime="text/csv",
    )

    # --- Forecast and risk ---
    risk = result["risk"]
    lo_all, hi_all = risk["overall_ci"]
    st.subheader("Forecast and risk")
    for msg in result["fallbacks"]:
        st.warning(msg)
    c1, c2 = st.columns(2)
    c1.metric("Chosen model", risk["model"])
    c2.metric(
        f"Overall P(wrong) at {tol_pct}% tolerance",
        f"{risk['p_wrong_overall']:.2f}",
        help=f"95% CI [{lo_all:.2f}, {hi_all:.2f}]",
    )
    st.caption(f"Overall 95% CI: [{lo_all:.2f}, {hi_all:.2f}]. Series resampled to {N_RESAMPLE} points.")

    fig = forecast_figure(result["x"], result["y"], result["x_future"], risk["forecast"], risk["model"])
    st.pyplot(fig)
    plt.close(fig)

    st.dataframe(
        risk_table(result["x_future"], risk).style.format(
            {"x": "{:.2f}", "forecast": "{:.2f}", "P(wrong)": "{:.2f}", "CI low": "{:.2f}", "CI high": "{:.2f}"}
        ),
        hide_index=True,
    )
    st.caption(
        "P(wrong) is the share of past rolling-validation forecasts at that step that missed by more "
        "than the tolerance. Windows overlap, so the interval is optimistic."
    )


main()
