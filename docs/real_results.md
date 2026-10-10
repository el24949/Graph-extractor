# Real-chart results

The pipeline (`extract_series` with no axis limits: plot-area detection, then
line isolation) was run on five real chart screenshots in `samples/real/`,
three times as it was improved:

1. **First version:** built and tuned only on clean synthetic charts.
2. **After the detection fix:** plot-area detection made robust to screenshot
   frames, gray axes and charts with only gridlines; boxes validated. Line
   isolation unchanged.
3. **After the line fix (now):** line isolation lists the line colours, lets
   the user pick one (`target_hue`), follows one line column by column instead
   of taking the median of everything, and no longer extrapolates past the
   ends of the line. Plot-area detection unchanged.

**Now: 3 worked, 1 partly, and `real_01` fails on Auto but works with a manual
plot box** (set by hand in the app or with `--box`). The colour used for each chart is
listed; "Auto" (no colour chosen) is described where it differs.

Result meanings:

- **worked:** correct plot box and the extracted line follows the chosen line.
- **partly:** the output is wrong in places, or the box has a problem that
  makes calibration hard.
- **failed (error):** no plot area found.
- **failed (wrong output):** it ran, but the box was invalid, so the output is
  not usable.

**About these images.** They are screenshots of charts published by other
people and organisations (sources below). They are included only to test this
tool, and all rights remain with their owners. If you own one of these images
and want it removed, please open an issue.

| chart | what it is | source | first version | after detection fix | after line fix (now) | colour used | cause (now) |
|---|---|---|---|---|---|---|---|
| `real_01` | DAX index, intraday, green line with filled area | [Google Finance, DAX (DAX:INDEXDB)](https://www.google.com/finance/quote/DAX:INDEXDB) | failed (error) | failed (error) | **failed (error) on Auto; worked with a manual box** | 1 (`#046e00`, the only colour, found inside the manual box) | Automatic detection still fails (no axes; the fill hides the gridlines). With a manual box (80, 40, 810, 241), placed on the 25,200 and 24,800 labels and the 9:00 and 20:00 positions measured from the gridlines, the line is extracted correctly: about 24,980 at 9:06, a high of 25,157 at about 15:38 and about 25,087 at the end, matching the chart. The fill under the line is ignored. The result is only as good as the box: 1 px is about 2 index points. |
| `real_02` | NOAA global temperature anomalies, two lines (blue, red) | [NOAA NCEI, Global Historical Climatology Network daily (GHCNd)](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily) | failed (wrong output) | partly | **worked** | 1 (`#e34230`, the red v5.1.0 series) | The NOAA logo is no longer picked up: with the red colour chosen it is excluded, and even on Auto the tracker stays on the line instead of jumping to the logo. The line now ends at 2022 instead of running flat into the margin. Where the blue series is drawn over the red one, the red is hidden for a few pixels and those columns are interpolated. |
| `real_03` | Daily rainfall, Excel-style, dates on x-axis | [Microsoft Support, "Present your data in a scatter chart or a line chart"](https://support.microsoft.com/en-us/excel/present-your-data-in-a-scatter-chart-or-a-line-chart) | failed (error) | worked | **worked** | 1 (`#205f73`, the only colour) | Unchanged box (from gridlines). The flat extension after the last point (1/9/2007) is gone: the series now ends where the data ends. The date axis still has to be entered as numbers. |
| `real_04` | Matplotlib "Line Plot with Grid", two lines (blue, orange) | [Springer Nature, article doi:10.1007/s43545-025-01165-y](https://link.springer.com/article/10.1007/s43545-025-01165-y) | failed (wrong output) | partly | **worked (with a colour chosen)** | 2 (`#4887b2`, blue); 1 (`#ee9548`, orange) also works | Each line can now be extracted on its own by picking its colour; both follow their line. The flat ends are gone. Sharp peak tips are cut a little (spike flattening). On **Auto** it is still wrong: the tracker follows the orange line but switches to the blue one where they cross (around x = 33-36). |
| `real_05` | Speed vs time, blue line with circle markers, dense grid | [Wikipedia, "Line chart"](https://en.wikipedia.org/wiki/Line_chart) | failed (error) | partly | **partly** | 1 (`#0f06df`, the only colour) | Line now follows the curve through the markers and ends at the last marker (no flat tail), with small hooks where it passes the hollow circles. Still partly because of the box, not the line: the y-axis is cut off at the top of the screenshot, so the box top is the image edge (row 0), which is not a labelled value, and calibrating y needs the value at that row. |

Detection notes (unchanged from the detection fix): `real_01` has no axis
lines, and in the gridline fallback the light green fill under the line counts
as "ink", forms wide solid blocks that swallow the vertical gridlines inside
them, and is rejected as too thick to be a line, leaving only one usable
gridline.

Overlays: `docs/overlays/real/real_XX_overlay.png` (`real_01` with the manual box; plus
`real_04_orange_overlay.png` for the orange line). The extracted line is drawn
in red (magenta on `real_02`, whose chosen series is itself red), the green
rectangle is the detected plot box, and the label at the top says how the box
was found, which colour was used and the x-range extracted.
