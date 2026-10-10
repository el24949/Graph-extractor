# Graph Extractor

A tool for extracting time series data from images of graphs.

## Problem

<!-- TODO -->

## Pipeline

### Step 2: Synthetic charts with ground truth

`src/generate_samples.py` draws 15 line charts (trend, seasonal, random walk,
trend + seasonal) with different colours, line widths, grids and image sizes.
For each `samples/chart_XX.png` it also saves the exact data that was plotted
(`chart_XX_truth.csv`) and the axis limits and plot-area box
(`chart_XX_meta.json`). Seeds are fixed, so every run produces the same
charts. Having the true data lets us measure how accurate each step is.

The extraction code never reads the meta files. Only the tests use them, to
check the results.

### Step 3A: Find the plot area

`detect_plot_area` in `src/extract.py` looks for the axis lines. It keeps only
dark pixels, then uses morphological opening with long, thin kernels so that
only long straight lines survive. Text, ticks and the data line are too short
and disappear. The x axis gives the bottom and right edges; the y axis gives
the left and top edges.

### Step 3B: Isolate the line

`extract_line_pixels` looks just inside the plot area (3 px in, to stay clear
of the axes). It picks out coloured pixels using HSV saturation, which skips
the white background, grey grid and black axes. For each pixel column it takes
the middle (median) of the line's pixels, and fills empty columns by
interpolation.

Black or grey lines have no colour, so if fewer than 100 coloured pixels are
found it switches to dark pixels instead (grayscale below 80). It reports which
mode it used: `"color"` or `"dark"`.

### Step 3C: Convert pixels to values

`calibrate` in `src/calibrate.py` maps pixels to data values with a straight
line through two reference points per axis: left edge to `xmin`, right edge to
`xmax`, bottom edge to `ymin`, top edge to `ymax`. Pixel rows count downward
but values go up, so the y mapping is flipped. Using bottom to `ymin` and top
to `ymax` as the references handles this automatically.

For now the axis limits come from the meta files. Reading them from the tick
labels is a later step.

## Install

<!-- TODO -->

## Usage

<!-- TODO -->

## Results

<!-- TODO -->

## Limitations

- **Easier than real charts.** The sample charts hide their top and right
  borders, and there is nothing else inside the plot area. Real charts often
  have a full frame, legends, labels and several lines, so finding the plot
  area there is harder.
- **The dark fallback picks up anything dark.** Dark text, markers or a legend
  inside the plot area get mixed in with the line and pull the result off.
- **Black or grey lines rely on the fallback.** They only work through the
  dark-pixel mode. Mid-grey lines (lighter than grayscale 80) match neither
  mode and fail.
- **Sharp spikes get flattened.** Taking one value per pixel column cuts the
  tips off narrow peaks, and the first and last few pixels next to the axes
  are not measured. Noisy charts with steep jumps have the largest error.
- **One line per chart.** With several lines, the column median falls between
  them.
