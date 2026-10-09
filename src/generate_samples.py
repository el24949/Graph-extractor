"""Generate synthetic time series line charts with ground truth data.

Each chart is saved as samples/chart_XX.png alongside:
  - samples/chart_XX_truth.csv: the exact (x, y) data that was plotted
  - samples/chart_XX_meta.json: axis limits and the plot-area pixel bounding box

Run from the project root:
    python -m src.generate_samples
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

KINDS = ("trend", "seasonal", "random_walk", "trend_seasonal")


def make_series(n, seed, kind):
    """Return a length-n numpy array of the given kind with Gaussian noise added.

    Kinds: "trend", "seasonal", "random_walk", "trend_seasonal".
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)

    if kind == "trend":
        slope = rng.uniform(-0.5, 0.5)
        base = 50 + slope * t
        noise_scale = 2.0
    elif kind == "seasonal":
        period = rng.uniform(n / 8, n / 3)
        amplitude = rng.uniform(5, 20)
        base = 50 + amplitude * np.sin(2 * np.pi * t / period + rng.uniform(0, 2 * np.pi))
        noise_scale = amplitude * 0.1
    elif kind == "random_walk":
        base = 50 + np.cumsum(rng.normal(0, 1.0, n))
        noise_scale = 0.3
    elif kind == "trend_seasonal":
        slope = rng.uniform(-0.4, 0.4)
        period = rng.uniform(n / 8, n / 3)
        amplitude = rng.uniform(5, 15)
        base = 50 + slope * t + amplitude * np.sin(2 * np.pi * t / period)
        noise_scale = amplitude * 0.1
    else:
        raise ValueError(f"Unknown kind {kind!r}; expected one of {KINDS}")

    return base + rng.normal(0, noise_scale, n)


def render_chart(x, y, path, color, linewidth, grid, figsize, dpi):
    """Draw y against x as a single clean line chart and save it to path.

    Returns a dict with the axis limits and the plot-area bounding box in
    image pixel coordinates (origin top-left, y pointing down).
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, facecolor="white")
    ax.set_facecolor("white")
    ax.plot(x, y, color=color, linewidth=linewidth)

    margin = 0.05 * (y.max() - y.min())
    ax.set_xlim(x.min(), x.max())
    ax.set_ylim(y.min() - margin, y.max() + margin)
    if grid:
        ax.grid(True, color="#dddddd", linewidth=0.8)
    else:
        ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.canvas.draw()

    # Axes extent is in display pixels with origin bottom-left; flip to image coords.
    _, height = fig.canvas.get_width_height()
    bbox = ax.get_window_extent()
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    # No bbox_inches="tight": the saved image must match the canvas pixel-for-pixel.
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)

    return {
        "xmin": float(xmin),
        "xmax": float(xmax),
        "ymin": float(ymin),
        "ymax": float(ymax),
        "plot_bbox_px": {
            "left": float(bbox.x0),
            "right": float(bbox.x1),
            "top": float(height - bbox.y1),
            "bottom": float(height - bbox.y0),
        },
    }


def main():
    """Generate 15 charts with varied styles, plus their truth CSV and meta JSON."""
    SAMPLES_DIR.mkdir(exist_ok=True)

    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#000000", "#17becf", "#8c564b"]
    linewidths = [1.0, 1.5, 2.0, 2.5, 3.0]
    figsizes = [(8, 4), (6, 4), (10, 5), (7, 3.5), (9, 6)]
    dpis = [100, 120, 80]
    lengths = [100, 150, 200, 300]

    for i in range(15):
        seed = 1000 + i
        kind = KINDS[i % len(KINDS)]
        n = lengths[i % len(lengths)]

        x = np.arange(n, dtype=float)
        y = make_series(n, seed, kind)

        name = f"chart_{i + 1:02d}"
        # i % 3 rather than i % 2 so grid on/off is not tied to the kind cycle.
        grid = i % 3 != 0
        meta = render_chart(
            x,
            y,
            SAMPLES_DIR / f"{name}.png",
            color=colors[i % len(colors)],
            linewidth=linewidths[i % len(linewidths)],
            grid=grid,
            figsize=figsizes[i % len(figsizes)],
            dpi=dpis[i % len(dpis)],
        )

        pd.DataFrame({"x": x, "y": y}).to_csv(SAMPLES_DIR / f"{name}_truth.csv", index=False)

        meta.update({"kind": kind, "seed": seed, "n": n})
        with open(SAMPLES_DIR / f"{name}_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        print(f"{name}: kind={kind}, n={n}, grid={grid}")


if __name__ == "__main__":
    main()
