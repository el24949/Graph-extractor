# Real-chart results

The pipeline (`extract_series` with no axis limits: plot-area detection, then
line isolation) was run on five real chart screenshots in `samples/real/`.

- **Before:** the first version, built and tuned only on clean synthetic
  charts. It failed on all five.
- **After:** plot-area detection made robust to screenshot frames, gray axes
  and charts with only gridlines, and boxes are now validated. Line isolation
  (`extract_line_pixels`) was **not** changed.

**After the change: 1 worked, 3 partly, 1 still failed.** Most of the
remaining problems are in line isolation, which was not touched.

Result meanings:

- **worked:** correct plot box and the extracted line follows the chart's line.
- **partly:** correct (or nearly correct) plot box, but the line or the box has
  a problem that makes the output wrong in places.
- **failed (error):** no plot area found.
- **failed (wrong output):** it ran, but the box was invalid, so the output is
  not usable.

**About these images.** They are screenshots of charts published by other
people and organisations (sources below). They are included only to test this
tool, and all rights remain with their owners. If you own one of these images
and want it removed, please open an issue.

| chart | what it is | source | before | after | cause (after) |
|---|---|---|---|---|---|
| `real_01` | DAX index, intraday, green line with filled area | [Google Finance, DAX (DAX:INDEXDB)](https://www.google.com/finance/quote/DAX:INDEXDB) | failed (error) | **failed (error)** | Still no plot area. There are no axis lines, and the gridline fallback fails too: the light green fill under the line counts as "ink", forms wide solid blocks that swallow the vertical gridlines inside them, and is rejected as too thick to be a line. Only one usable gridline is left. |
| `real_02` | NOAA global temperature anomalies, two lines (blue, red) | [NOAA NCEI, Global Historical Climatology Network daily (GHCNd)](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily) | failed (wrong output) | **partly** | Box now correct (the black bar at the top is ignored as a border line; the bottom axis is chosen over the top frame and the zero line). The legend is now outside the box, so the 1850s spikes are gone. Still wrong: the line drops onto the blue NOAA logo around 2010-2018, because the logo is inside the plot area. The two series mostly overlap, so elsewhere it follows them. |
| `real_03` | Daily rainfall, Excel-style, dates on x-axis | [Microsoft Support, "Present your data in a scatter chart or a line chart"](https://support.microsoft.com/en-us/excel/present-your-data-in-a-scatter-chart-or-a-line-chart) | failed (error) | **worked** | Box found from the gridlines (mode `grid`): top and bottom are the 8 and 0 gridlines, and the sides are where the gridlines end. The line is traced closely. Caveat: the data ends before the box's right edge, so the last value is extended flat to the edge, and the date axis has to be entered as numbers. |
| `real_04` | Matplotlib "Line Plot with Grid", two lines (blue, orange) | [Springer Nature, article doi:10.1007/s43545-025-01165-y](https://link.springer.com/article/10.1007/s43545-025-01165-y) | failed (wrong output) | **partly** | Box now correct (the 1 px screenshot frame is ignored; the full matplotlib box is found). Line still unusable: with two coloured lines, the per-column median jumps between them, and the value is extended flat across the plot margins at both ends. |
| `real_05` | Speed vs time, blue line with circle markers, dense grid | [Wikipedia, "Line chart"](https://en.wikipedia.org/wiki/Line_chart) | failed (error) | **partly** | The mid-gray axes are now found (the looser darkness threshold catches them). Left, bottom and right edges are correct and the line is traced well through the markers. But the y-axis is cut off at the top of the screenshot, so the box top is the image edge (row 0), which is not a labelled value, and calibrating y needs the value at that row. The value after the last point is extended flat to the right edge. |

Overlays: `docs/overlays/real/real_XX_overlay.png`. The red line is the
extracted line, the green rectangle is the detected plot box, and the label at
the top says how the box was found (`axes` or `grid`) or why it failed.
