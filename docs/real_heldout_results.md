# Held-out real-chart results

Four real chart images (`samples/real_heldout/chart1.jpg` to `chart4.jpg`)
that were **not used while building or fixing the pipeline**. Each was run
**once**, with the code as of commit `c7c0b49`, before any change, and the
result was recorded as it came. Nothing was tuned after seeing it.

**Flow used (the normal one):** Auto plot box first, Manual only if Auto
fails. Auto found a box on all four (method `axes`), so no manual box was
used. The line colour was chosen from `find_series_colors` (the
`--list-colors` list) **before** extracting: the only colour where there is
one, and on `chart4` the red five-year average (the blue colour there is only
the markers on a black line).

**Result** is judged visually from the overlay, with the same definitions as
`docs/real_results.md`:

- **worked:** correct plot box and the extracted line follows the chosen line.
- **partly:** the output is wrong in places, or the box has a problem that
  makes calibration hard.
- **failed (error):** no plot area found.
- **failed (wrong output):** it ran, but the output is not usable.

There is **no numeric ground truth** for these images; the result is what the
overlay shows, not a measured error.

**Axis limits were read by eye** from the tick labels, not measured:

| chart | xmin | xmax | ymin | ymax | note |
|---|---:|---:|---:|---:|---|
| `chart1` | 0 | 5 | 0 | 6 | |
| `chart2` | 0 | 2015 | 0 | 25 | **uncertain:** xmin = 0 may be wrong (first label is 1916) |
| `chart3` | 0 | 2006 | 0 | 12 | **uncertain:** xmin = 0 may be wrong (first label is 2002) |
| `chart4` | 1880 | 2000 | -0.4 | 0.6 | |

## Results (one run, before any fix)

| chart | what it is | source | box mode | colour used | result | cause | after (ticks): post-hoc, no longer held-out |
|---|---|---|---|---|---|---|---|
| `chart1` | Matplotlib "Basic Line Plot Example", one blue line, dashed grid | unknown | auto (`axes`, box 80, 59, 576, 427) | 1 (`#346e95`, the only colour) | **worked** | Box on the axes; the extracted line lies on the blue line from the first to the last point, corners included. | Same line (calibration does not change extraction). **Values plausible:** every vertex within 0.04 of the chart, e.g. peak (4, 6) -> (4.00, 5.96), (2, 4) -> (2, 3.98). |
| `chart2` | Minitab-style "Time Series Plot of Quakes", blue line with dot markers, gray frame | unknown | auto (`axes`, box 56, 48, 549, 329) | 1 (`#104d88`, the only colour) | **worked** | Box on the axes; the gray background outside it is ignored. The line follows the series end to end through the markers. Some sharp single-year peaks are cut a little (spike flattening), most visibly the 1931 peak (19), which reaches about 17 in the overlay. | Same line. **Values plausible overall:** first point (1916, 2) -> (1915.8, 2.1), maximum (2010, 24) -> (2010.3, 24.0), last (2015, 19) -> (2015.4, 19.0). Sharp single-year extremes are 1-2 quakes too small (1931: 19 -> 16.9; 1945: 5 -> 6.5), from the spike flattening above. |
| `chart3` | Black line with black dot markers on a heavy black grid ("Sales in Rs Crores", 2002-2006) | unknown | auto (`axes`, box 179, 56, 1021, 799) | none (no coloured pixels: dark fallback) | **failed (wrong output)** | The box is correct (outer frame of the grid), but the line is wrong. The chart's line is black and the gridlines are black and almost as thick, so the dark fallback keeps both. The tracker starts on a horizontal gridline (the y = 7 line), follows it across the whole plot, and only touches the real line between about 2003 and 2004. Note: the box itself is fine, unlike the "box invalid" case this label was defined for; it is listed as failed because the output is unusable over most of the x-range. | Same wrong line, so **values not plausible:** y stays between 5.9 and 7.3 (the y = 7 gridline), while the chart goes from 4 to 10. x is now in years (2001.3 to 2006.7, the whole grid width). |
| `chart4` | "Global Temperatures": black line with blue markers (annual) and a thick red line (five-year average), dotted grid, in-plot legend | unknown | auto (`axes`, box 153, 42, 929, 685) | 2 (`#f50100`, red five-year average) | **worked** | Box on the axes. The extracted line follows the red curve from start to end and ignores the blue markers, the black line and the red legend sample. At the right end it runs a few pixels flat past the visible end of the red line (around 2006-2008). | Same line. **Values plausible:** low about (1909, -0.40) -> (1909.2, -0.400); 1943 peak about 0.02 -> 0.01; 1990 about 0.20 -> 0.20; 2000 about 0.35 -> 0.37. The flat tail past the red line's end runs to 2008.7. |

**Counts: 3 worked, 0 partly, 1 failed.** Auto box: 4 of 4 found, all correct.

**After (ticks), post-hoc, no longer held-out:** with reference-tick
calibration the calibrated values are plausible on 3 of 4 (`chart1`, `chart2`,
`chart4`) and not plausible on `chart3`, whose line was already wrong.

## Calibrated values: wrong on all four with these limits

The result above is about the extracted line in pixels. The calibrated numbers
are a separate matter, and they are off on all four charts. This is not a
line-extraction problem: the pipeline pairs `xmin`/`xmax`/`ymin`/`ymax` with
the **edges of the plot box**, but the limits here were read from the **first
and last tick labels**, which are not at the box edges on any of these charts.

Spot checks (extracted value vs what the chart shows):

| chart | point on the chart | extracted | why |
|---|---|---|---|
| `chart1` | peak at (4, 6) | (3.63, 5.72) | The box runs from about x = 0.8 to 5.2 and y = 0.75 to 6.25 (estimated from the tick positions), not 0-5 and 0-6. |
| `chart2` | first point (1916, 2) | (45, 2.4) | xmin = 0 is wrong (as flagged): the box's left edge is about 1914, so every x is shifted by roughly 1,870 years. y is off by about 0.4 at the bottom. |
| `chart3` | n/a (line is wrong) | x from 7 to 1996 | Same xmin = 0 problem; the box top is about 13.9, not 12. |
| `chart4` | red line low at about (1909, -0.40) | (1906, -0.31) | The box bottom is about -0.5, not -0.4, and the right edge is about 2013, not 2000, so y is squeezed at the bottom and x is compressed. |

So on these four charts, with limits typed the way a user naturally reads
them (from the tick labels), the numbers are usable on none of them without
correcting the limits to the box edges. This was a known design limitation at the time (calibrating from two
labelled gridlines instead of the box edges was listed as future work), and
this test showed it matters in practice, not only for manual boxes. It led to
the reference-tick calibration below.

## After: reference-tick calibration (post-hoc, no longer held-out)

**This is not a held-out result.** The reference-tick calibration was added
after the run above, and the ticks were measured after its results had been
seen. The extraction itself (box, colour, line) is unchanged, so the overlays
are the same line; only the pixel -> value map is different.

Ticks were measured from the image, not read by eye: the centre of each tick
mark (or gridline) found from the darkness profile next to the axis, then
matched to its label. Pixels are full-image coordinates.

| chart | x ticks (pixel, value) | y ticks (pixel, value) | measured from |
|---|---|---|---|
| `chart1` | (103, 1.0), (553, 5.0) | (410, 1), (74, 6) | tick marks outside the axes |
| `chart2` | (68, 1916), (536, 2015) | (325, 0), (52, 25) | light gray tick marks outside the axes |
| `chart3` | (287.5, 2002), (913.5, 2006) | (695.5, 2), (158.5, 12) | gridlines (no tick marks). **Ambiguous on x:** the year labels are evenly spaced, but the dots sit on gridlines 8-25 px right of the label centres; the gridlines under the 2002 and 2006 dots were used |
| `chart4` | (268.4, 1900), (840.5, 2000) | (628.0, -0.4), (160.0, 0.4) | dotted gridlines |

Spot checks (value read from the chart -> extracted value at that x):

| chart | checks | plausible? |
|---|---|---|
| `chart1` | (1, 2) -> 2.02; (2, 4) -> 3.98; (3, 1) -> 1.02; (4, 6) -> 5.96; (5, 3) -> 3.02; midpoints 2.5 -> 2.48, 3.5 -> 3.53, 4.5 -> 4.49 | **yes**, within 0.04 (about 0.7% of the range) |
| `chart2` | first (1916, 2) -> 2.1; max (2010, 24) -> 24.0 at 2010.3; last (2015, 19) -> 19.0; 1968 (22) -> 21.1; 1957 (21) -> 19.9; 1980 (6) -> 6.2; 1931 (19) -> 16.9; 1945 (5) -> 6.5 | **yes overall**; one-year peaks and dips are 1-2 too flat (up to about 2 quakes, 8% of the range) |
| `chart3` | y from 5.9 to 7.3; the chart's points are 4, 7, 6, 10, 8 | **no**: the line is the y = 7 gridline, so the values are wrong whatever the calibration |
| `chart4` | about (1909, -0.40) -> -0.40; 1900 (-0.22) -> -0.23; 1943 (0.02) -> 0.01; 1950 (-0.12) -> -0.12; 1966 (-0.13) -> -0.12; 1990 (0.20) -> 0.20; 2000 (0.35) -> 0.37 | **yes**, within about 0.02; the last 2-3 years are a flat tail past the line's end |

The chart values here were read by eye from the images, so these checks show
plausibility, not a measured error. Overlays with the ticks drawn (blue
vertical lines for x, orange horizontal lines for y):
`docs/overlays/real_heldout/chartN_ticks_overlay.png`.

## Limits of this test

- **n = 4 is too small to generalise.** It is a sanity check on unseen charts,
  not an accuracy estimate.
- Judged visually from the overlays; no numeric ground truth.
- Axis limits were read by eye; two of them (`chart2` and `chart3` xmin) are
  marked uncertain and are in fact wrong for the box edges.
- Sources are unknown. All rights remain with the images' owners; they are
  included only to test this tool. If you own one and want it removed,
  please open an issue.

Overlays: `docs/overlays/real_heldout/chartN_overlay.png`. The extracted line
is drawn in red (magenta on `chart4`, whose chosen series is itself red), the
green rectangle is the plot box, and the label at the top gives the box
method, the colour used, the line mask mode and the pixel x-range extracted.
