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
from src.pipeline import UNITS_RELATIVE, UNITS_TEXT, extract_series, series_colors  # noqa: E402
from src.risk import forecast_with_risk  # noqa: E402

N_RESAMPLE = 100

VALUES_RELATIVE = "Relative (% of plot area)"
VALUES_LIMITS = "Real limits (box edges)"
VALUES_TICKS = "Reference ticks"


def analyze(img_path, x_ref, y_ref, tol_pct, h, target_hue=None, box=None, x_ticks=None, y_ticks=None):
    """Run extraction, overlay, resampling and forecast_with_risk on one image.

    box: a manual (left, top, right, bottom) plot box, or None to detect it.
    x_ticks, y_ticks: two (pixel, value) reference ticks per axis, used instead
    of the box-edge limits x_ref, y_ref (pass None for those). With neither,
    the values are relative (0-100% of the plot box); result["units"] says which.

    Returns a dict of everything the page shows. Raises ValueError with a
    readable message for the failures the page reports.
    """
    # Pixel run for the overlay, calibrated run for the data. src/ is left
    # unchanged, so this calls the pipeline twice rather than re-mapping.
    px_df, mode, box, box_mode = extract_series(img_path, target_hue=target_hue, box=box, pixels=True)
    df, *_ = extract_series(img_path, x_ref, y_ref, target_hue=target_hue, box=box, x_ticks=x_ticks, y_ticks=y_ticks)

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
        "units": df.attrs["units"],
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


def default_manual_box(width, height):
    """A starting box for manual mode: the middle 80% of the image."""
    return (round(0.1 * width), round(0.1 * height), round(0.9 * width) - 1, round(0.9 * height) - 1)


def box_preview(img_bgr, box):
    """RGB copy of the image with the box drawn in green, for the live preview."""
    preview = img_bgr.copy()
    left, top, right, bottom = box
    thickness = max(1, round(min(img_bgr.shape[:2]) / 300))
    cv2.rectangle(preview, (left, top), (right, bottom), (0, 180, 0), thickness)
    return cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)


def calibration_preview(img_bgr, box, x_ticks, y_ticks):
    """RGB copy of the image with the box in green and the reference ticks as
    lines: vertical blue lines for the x ticks, horizontal orange lines for the
    y ticks, each labelled with its value."""
    preview = cv2.cvtColor(box_preview(img_bgr, box), cv2.COLOR_RGB2BGR)
    height, width = img_bgr.shape[:2]
    thickness = max(1, round(min(height, width) / 300))
    scale = max(0.4, min(height, width) / 800)
    for px, val in x_ticks:
        x = int(round(px))
        cv2.line(preview, (x, 0), (x, height - 1), (200, 80, 0), thickness)
        cv2.putText(preview, f"x={val:g}", (x + 3, int(14 * scale) + 4), cv2.FONT_HERSHEY_SIMPLEX, scale, (200, 80, 0), 1, cv2.LINE_AA)
    for py, val in y_ticks:
        y = int(round(py))
        cv2.line(preview, (0, y), (width - 1, y), (0, 140, 255), thickness)
        cv2.putText(preview, f"y={val:g}", (3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 140, 255), 1, cv2.LINE_AA)
    return cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)


def swatch_html(hex_color, label):
    """A small coloured square followed by a label, for st.markdown."""
    return (
        f'<span style="display:inline-block;width:14px;height:14px;background:{hex_color};'
        f'border:1px solid #888;margin-right:6px;vertical-align:middle"></span>{label}'
    )


def forecast_figure(x, y, x_future, forecast, model, relative=False):
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
    ax.set_xlabel("x (% of plot width)" if relative else "x")
    ax.set_ylabel("y (% of plot height)" if relative else "y")
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
        tol_pct = st.slider("Tolerance (% of range)", min_value=1, max_value=30, value=10)
        h = st.slider("Forecast horizon h", min_value=5, max_value=20, value=10)

    if uploaded is None:
        st.info(
            "Upload a line chart image in the sidebar to start. Values are relative "
            "(% of the plot area) unless you give real axis values under Advanced."
        )
        return

    # Save the upload to a temp file so the pipeline can read it by path.
    suffix = Path(uploaded.name).suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(uploaded.getvalue())
        tmp.close()
        img = cv2.imread(tmp.name)
        if img is None:
            raise FileNotFoundError(tmp.name)
        height, width = img.shape[:2]

        # Try automatic plot-area detection first.
        auto_box, auto_error, colors = None, None, []
        try:
            auto_box, _, colors = series_colors(tmp.name)
        except ValueError as exc:
            auto_error = str(exc)

        # The line colour picker is shown above Advanced but filled in after it,
        # because a manual box changes which colours are found.
        colour_area = st.sidebar.container()
        upload_key = f"{uploaded.name}-{uploaded.size}"

        # Advanced: real axis values, manual plot box, reference ticks. Opened
        # by itself when detection fails, since the box must then be set by hand.
        with st.sidebar.expander("Advanced", expanded=bool(auto_error)):
            values = st.radio(
                "Axis values",
                [VALUES_RELATIVE, VALUES_LIMITS, VALUES_TICKS],
                key=f"values-{upload_key}",
                help="Relative: x and y in % of the plot area, no input needed. "
                "Real limits: the axis values at the edges of the plot box. "
                "Reference ticks: two labelled ticks per axis (pixel position and value).",
            )
            x_ref = y_ref = x_ticks = y_ticks = None
            if values == VALUES_LIMITS:
                st.caption("Axis values at the edges of the plot box (not the first and last tick labels)")
                c1, c2 = st.columns(2)
                xmin = c1.number_input("xmin", value=0.0, key=f"xmin-{upload_key}")
                xmax = c2.number_input("xmax", value=100.0, key=f"xmax-{upload_key}")
                ymin = c1.number_input("ymin", value=0.0, key=f"ymin-{upload_key}")
                ymax = c2.number_input("ymax", value=100.0, key=f"ymax-{upload_key}")
                x_ref, y_ref = (xmin, xmax), (ymin, ymax)

            # Plot box: Auto, or Manual with sliders. If detection failed, Manual
            # is selected for a new upload and starts from the middle 80% of the image.
            box_choice = st.radio(
                "Plot box",
                ["Auto", "Manual"],
                index=1 if auto_error else 0,
                horizontal=True,
                key=f"box_choice-{upload_key}",
            )
            manual_box = None
            if box_choice == "Manual":
                start = auto_box or default_manual_box(width, height)
                st.caption(f"Plot box in pixels (image is {width} x {height})")
                manual_box = (
                    st.slider("left", 0, width - 1, start[0], key=f"left-{upload_key}"),
                    st.slider("top", 0, height - 1, start[1], key=f"top-{upload_key}"),
                    st.slider("right", 0, width - 1, start[2], key=f"right-{upload_key}"),
                    st.slider("bottom", 0, height - 1, start[3], key=f"bottom-{upload_key}"),
                )

            # Reference ticks: two (pixel, value) points per axis, in full-image
            # pixels. They start on the box edges; move them onto labelled ticks.
            if values == VALUES_TICKS:
                start = manual_box or auto_box or default_manual_box(width, height)
                st.caption(f"Reference ticks: pixel (full image, {width} x {height}) and value")
                x_ticks, y_ticks = [], []
                for axis, pixels, store in (("x", (start[0], start[2]), x_ticks), ("y", (start[3], start[1]), y_ticks)):
                    for i, px in enumerate(pixels, 1):
                        c1, c2 = st.columns(2)
                        limit = (width if axis == "x" else height) - 1
                        p = c1.number_input(f"{axis} tick {i} pixel", 0, limit, int(px), key=f"{axis}{i}px-{upload_key}")
                        v = c2.number_input(f"{axis} tick {i} value", value=float(i - 1) * 100, key=f"{axis}{i}val-{upload_key}")
                        store.append((p, v))
                x_ticks, y_ticks = tuple(x_ticks), tuple(y_ticks)

        if x_ref is not None and (x_ref[0] >= x_ref[1] or y_ref[0] >= y_ref[1]):
            st.error("Axis limits must satisfy xmin < xmax and ymin < ymax (Advanced, in the sidebar).")
            return

        if auto_error:
            st.error(f"Automatic plot-area detection failed: {auto_error}")
            if box_choice == "Auto":
                st.info("Switch Plot box to Manual under Advanced in the sidebar to set the plot area by hand.")
                return
            st.info("Manual mode is on (Advanced, in the sidebar). Drag the sliders until the green box sits on the plot area.")

        if manual_box is not None or x_ticks is not None:
            if x_ticks is not None:
                st.subheader("Calibration preview")
                st.image(
                    calibration_preview(img, manual_box or auto_box, x_ticks, y_ticks),
                    caption="Green: plot box. Blue: x reference ticks. Orange: y reference ticks. "
                    "Each line should sit on the tick whose value you entered.",
                    width="stretch",
                )
            else:
                st.subheader("Plot box preview")
                st.image(box_preview(img, manual_box), caption=f"Manual box {manual_box}", width="stretch")
        if manual_box is not None:
            # Colours inside the manual box (also validates it).
            _, _, colors = series_colors(tmp.name, box=manual_box)

        # Line colours found in the plot area; the user picks which series to extract.
        with colour_area:
            st.caption("Line colours found in the plot area")
            if colors:
                st.markdown(
                    "<br>".join(swatch_html(c["hex"], f"{i}: {c['hex']} ({c['count']} px)") for i, c in enumerate(colors, 1)),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("None (no coloured pixels; a black or gray line uses the dark fallback).")
            choice = st.radio(
                "Line to extract",
                options=[0] + list(range(1, len(colors) + 1)),
                format_func=lambda i: "Auto (all coloured pixels)" if i == 0 else f"Colour {i}: {colors[i - 1]['hex']}",
            )
        target_hue = colors[choice - 1]["hue"] if choice else None
        chosen = colors[choice - 1]["hex"] if choice else "auto"

        result = analyze(tmp.name, x_ref, y_ref, tol_pct, h, target_hue, manual_box, x_ticks, y_ticks)
    except FileNotFoundError:
        st.error("Could not read the image. Is it a valid PNG or JPG?")
        return
    except ValueError as exc:
        msg = str(exc)
        if "Invalid manual box" in msg:
            st.error(f"{msg}. Adjust the sliders under Advanced in the sidebar.")
        elif "ticks" in msg and msg.startswith("Invalid"):
            st.error(f"{msg}. Adjust the reference ticks under Advanced in the sidebar.")
        elif "No plot area found" in msg or "Invalid plot area" in msg:
            st.error(f"No plot area found: no usable axis lines or gridlines. Details: {msg}")
        elif "chosen colour" in msg:
            st.error("No line of the chosen colour inside the plot area. Pick another colour or Auto.")
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
    relative = result["units"] == UNITS_RELATIVE
    st.write(
        f"Plot area from: **{result['box_mode']}**; units: **{UNITS_TEXT[result['units']]}**; "
        f"line colour: **{chosen}**; "
        f"line mask mode: **{result['mode']}**; "
        f"plot box (left, top, right, bottom): "
        f"({left}, {top}, {right}, {bottom}); {len(result['df'])} points extracted"
    )
    if relative:
        st.info(
            "Values are relative: x is % of the plot width and y is % of the plot height, "
            "not the chart's real values. P(wrong) and the chosen model barely depend on this "
            "(the tolerance is a % of the range). For real values, set them under Advanced in the sidebar."
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

    fig = forecast_figure(result["x"], result["y"], result["x_future"], risk["forecast"], risk["model"], relative)
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
