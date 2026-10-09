# Graph Extractor

A tool for extracting time series data from images of graphs.

## Problem

<!-- TODO -->

## Pipeline

<!-- TODO -->

## Install

<!-- TODO -->

## Usage

<!-- TODO -->

## Results

<!-- TODO -->

## Limitations

<!-- TODO -->

### Line detection: colour mask and dark fallback

`extract_line_pixels` finds the data line by colour first: inside the plot
area, pixels with HSV saturation above a threshold are treated as the line.
This ignores the white background, grey grid lines and black axes/text.

Black or grey lines have no saturation, so the colour mask comes back nearly
empty. When it has fewer than `min_color_pixels` pixels (default 100), the
function falls back to a dark-pixel mask (grayscale < 80) and returns
`mode="dark"` so callers can tell which path was used.

Limits of the fallback:

- **Anything dark inside the plot area counts as the line.** Text
  annotations, legends, markers or dark grid lines drawn inside the axes will
  be mixed into the per-column median and pull the result off the line.
- **Mid-grey lines are missed.** A line lighter than grayscale 80 (e.g.
  `#808080`) passes neither mask, and extraction raises an error.
- **Dark but coloured lines may switch modes unexpectedly.** A navy or dark
  red line can have low enough saturation to drop under the colour threshold
  in anti-aliased pixels; if the colour mask falls below `min_color_pixels`
  the dark mask is used instead.
- **Single series only.** Both masks assume exactly one line. With several
  series, the per-column median lands between them.
- **Tiny plots.** `min_color_pixels` is a fixed count, not scaled to image
  size. On a very small plot, a thin coloured line may have fewer than 100
  pixels and wrongly trigger the fallback.
