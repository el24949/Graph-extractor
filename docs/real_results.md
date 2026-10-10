# Real-chart results

The pipeline (plot-area detection and line isolation, `extract_series` with
no axis limits) was run unchanged on five real chart screenshots in
`samples/real/`. It was built and tuned only on the synthetic charts in
`samples/`, and **it failed on all five**.

"Failed (error)" means `detect_plot_area` raised "Could not find both axis
lines". "Failed (wrong output)" means it ran without an error but returned an
invalid plot box (bottom edge above the top edge), so the extracted line is
not usable.

| chart | what it is | result | cause |
|---|---|---|---|
| `real_01` | Stock index, intraday, green line with filled area | failed (error) | No axis lines at all: only light grey gridlines and a dotted baseline. No row is more than 11% dark. |
| `real_02` | NOAA global temperature anomalies, two lines (blue, red) | failed (wrong output) | A black bar across the top of the screenshot is the longest dark horizontal line, so it was taken as the x-axis (bottom = 0). Extraction then followed the red series in many places, but dropped onto the blue NOAA logo around 2010-2018, spiked toward the legend in the 1850s (the column median fell between line and legend), and ran flat into the right margin. |
| `real_03` | Daily rainfall, Excel-style, dates on x-axis | failed (error) | No axis lines: gridlines only. No row is more than 10% dark. |
| `real_04` | Matplotlib "Line Plot with Grid", two lines (blue, orange) | failed (wrong output) | A dark 1 px frame around the screenshot was taken as both axes (row 0, column 0), so the box is the whole image with bottom = 0. With two coloured lines, the per-column median jumps between them, and the line runs flat to both image edges. |
| `real_05` | Speed vs time, blue line with circle markers, dense grid | failed (error) | The axes are mid-grey (grayscale about 137-142), just lighter than the dark-pixel threshold (128), so they are dropped with the background. |

Overlays: `docs/overlays/real/real_XX_overlay.png`. The red line is the
extracted line, the green rectangle is the detected plot box, and the label at
the top says whether it ran or failed.
