# Figure Review Benchmark

Harness for the plot-review evaluation that backs the manuscript's primary claim
(automated publication-compliance figure review, including physical-property
estimation that general-purpose MLLMs do not reliably provide).

Scope is deliberately narrow: this covers the **50-figure boundary benchmark**,
the **50-figure semantic-compliance benchmark**, and the **cross-model
comparison**. It does not cover the 100-query five-task benchmark — that one
backs the integration claim, which the manuscript does not lead with.

## Why this exists

The thesis reports these results, but the repo has never contained the figure
set, the runner, the scoring rules, or the raw outputs. Re-running therefore
required reconstructing all four from prose. This directory exists so that never
happens again — **the four artifacts below are a delivery condition, not a
nice-to-have.**

Every run writes `runs/<timestamp>/` containing the git SHA, the model, the
execution path, and per-figure raw output. A number without that provenance is
not reportable.

## What still has to be filled in

### 1. `data/figures/` — the figure set

The images themselves. The thesis describes five chart types (PCA score,
volcano, heatmap, box, bar) with three compliance criteria toggled
independently. If they were generated programmatically, **commit the generator
instead of the PNGs** — that is strictly better, because it also pins how the
ground truth was derived.

### 2. `data/ground_truth.jsonl` — one record per figure

```json
{
  "figure_id": "pca_001",
  "path": "data/figures/pca_001.png",
  "chart_type": "pca_score",
  "resolution_dpi": 150,
  "font_size_pt": 8.0,
  "line_width_pt": 0.5,
  "axis_labels_complete": true,
  "colorblind_safe": false,
  "legend_overlapping": true
}
```

`chart_type` ∈ `pca_score | volcano | heatmap | box | bar`.
`font_size_pt` / `line_width_pt` are the **true continuous values** — they are
what the MAE / MAPE / RMSE / Pearson-r numbers are computed against, so an
approximation here silently caps the reported accuracy.

### 3. Scoring rules — already encoded and tested

The binary criteria and the continuous metrics are implemented in
`figure_bench.py` and covered by `test_stats.py` / `test_parse.py` (17 tests).
If the thesis used a different operational definition anywhere, fix it there
rather than post-processing the output.

Two defaults worth checking against how the thesis actually scored:

- **font size** is taken from `text_report.min_pt` (the smallest text, which is
  what publication limits constrain), not `avg_pt`. Both are recorded.
- **line width** is taken from `line_analysis.estimated_true_line_pt`, with
  `median_width_pt` recorded alongside.

A verdict the parser cannot read is **left absent, never defaulted** — the
scorer skips absent keys, whereas a wrong default would be counted as a correct
answer.

### 4. Raw outputs — produced automatically

`runs/<timestamp>/raw.jsonl`. Keep them in the repo (they are small).

## Execution path: the open question this also answers

`3b33cf5` and `ea99d51` mean that, before those fixes, a plot-review request
carrying a file was demoted to plain chat, and the structured `review_result`
never reached the API layer. **Whether the thesis numbers were affected depends
entirely on which path was used to produce them**, and nobody has written that
down.

So the runner supports both, and records which one ran:

```bash
# through the supervisor graph — real intent routing, real state passing
venv/bin/python -m benchmarks.figure_bench run --path agent

# the plot-review subgraph directly, bypassing intent routing
venv/bin/python -m benchmarks.figure_bench run --path node
```

`--path agent` invokes the compiled supervisor rather than going over HTTP,
because both defects in question live in the graph layer, not the API layer:
`3b33cf5` is `_correct_misclassification` demoting the request, `ea99d51` is
`MainState` not declaring the channel. Invoking the graph reproduces both while
avoiding a running server and a Postgres dependency — an in-memory checkpointer
is used for the same reason. **A benchmark must not require the production
database.**

Running both on the same figure set quantifies the gap. If they agree, the
routing fixes did not affect these results and the thesis numbers stand.

## Cross-model comparison

```bash
venv/bin/python -m benchmarks.figure_bench run --path node --model gpt-4.1-mini
venv/bin/python -m benchmarks.figure_bench run --path node --model gpt-5.4-mini
venv/bin/python -m benchmarks.figure_bench run --path node --model gemma4:26b
```

⚠️ The gemma path is currently **commented out** in `supervisor.py:36,40`,
`tools.py:17` and `literature_add.py:28`. If the manuscript keeps the
architectural-portability claim, that path has to be re-enabled and verified —
`gemma_tool.py` / `literature_gemma.py` exist but nothing calls them.

Then:

```bash
python -m benchmarks.figure_bench compare runs/<a> runs/<b>
```

which emits the paired comparison: per-criterion precision / recall / F1,
McNemar on the paired binary decisions, and Friedman across chart types for the
continuous metrics.

## Environment

Same as the app. In short:
`OPENAI_API_KEY`, the `meta_image:v3` R container, `PG_URL`, and `mummichog` in
the venv. Use `venv/bin/python`, not a bare `python`.

---

## Tables 12 and 13: already reproduced

`table12_13.py` recomputes the thesis's font-size and line-width accuracy from
`data/table12_13_measurements.csv` (50 rows exported from
`table9-15_rawdata.xlsx`, sheet `table_12&13_raw`). Every published figure is
pinned in `test_table12_13.py`.

```bash
venv/bin/python -m benchmarks.table12_13
venv/bin/python -m pytest benchmarks/ -q
```

This is the migration the manuscript needs: the thesis produced these numbers
by hand in a spreadsheet, where the font half had live formulas
(AVERAGE / SUMSQ / CORREL / STDEV.S) and the line half had only pasted values.
The code now reproduces **both halves exactly** — global MAE 0.9878 ± 0.8765
(font) and 0.2494 ± 0.2443 (line), and all ten per-chart-type figures.

### Where the arithmetic is written down

The original workbook had live formulas for the font half only; the line half
carried pasted values. `data/line_width_formulas_2026-08-28.xlsx`, supplied by
the author, is where the line arithmetic actually lives — `D = |median −
nominal|`, `MAPE = D / nominal`, `AVERAGE`/`STDEV.S`/`SUMSQ`/`CORREL` over the
50 rows. Both halves now reproduce exactly, including Pearson r (0.6954 font,
0.8818 line).

### The definition that was not obvious

`line error = |median_line_pt − nominal_line_pt|`, using the **median**
estimate, not `estimated_line_pt`. For 41 of 50 figures the two are identical,
so the distinction is invisible until the heatmaps: `benchmark_heatmap_03` has
nominal 2.0, median 2.06, estimated 6.25, and the thesis value is 0.06. Using
`estimated_line_pt` would inflate the heatmap MAE about tenfold.

### Why three chart types measure alike

**pca, volcano and boxplot share their line-width measurements**, figure for
figure. This was first read as a copy-paste defect. It is not.

`build_plot.py` generates all 50 figures as `PLOT_TYPES × PARAM_COMBOS`, and
every chart type gets the same line width sequence — 3, 1, 2, 1.5, 2.5, 2.5,
1.5, 1, 3, 2 — drawn from a single `line_pt` variable. The three line-dominated
types therefore measure alike. heatmap (colour fills) and bar_error (filled
rectangles) diverge because their line features genuinely differ. Confirmed by
the author on 2026-08-28.

Worth keeping in view rather than filing away: the agreement says the
distance-transform estimator is insensitive to chart type wherever real strokes
exist, and it explains why line-width MAE is the single metric whose Friedman
test came out non-significant — those groups do not differ, by construction.
Font size behaves differently: same nominal sizes, different measured values,
because the OCR-based estimator reacts to whatever else is on the canvas.

Both properties are pinned by tests
(`test_three_chart_types_share_line_width_by_construction`,
`test_nominal_line_widths_follow_the_generator_sequence`), so a regeneration
that changes the parameter grid will fail here rather than quietly shifting the
published numbers.
