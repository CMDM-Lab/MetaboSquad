# Figure Review Benchmark

Harness for the plot-review evaluation that backs the manuscript's primary claim
(automated publication-compliance figure review, including physical-property
estimation that general-purpose MLLMs do not reliably provide).

Scope is deliberately narrow: this covers the **50-figure boundary benchmark**,
the **50-figure semantic-compliance benchmark**, and the **cross-model
comparison**. The harness does not run the 100-query five-task benchmark —
that one backs the integration claim, which the manuscript does not lead with.
Its question set and recorded results are kept as data; see
[100-query five-task benchmark](#100-query-five-task-benchmark-data-only) below.

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

### 1. `data/figures/` — the figure set: generators committed

The figures were generated programmatically, and the generators supplied by
the author are in `generators/`. Each one writes the PNGs and a ground-truth
JSON, and the ground truth is the parameters the figure was drawn with.

| Generator | Figures | Ground-truth file | Manuscript |
| :--- | :--- | :--- | :--- |
| `build_plot.py` | 50 `benchmark_<type>_NN.png` (boundary: DPI, font, line width) | `benchmark_gt.json` | Tables S5, S7, S8 |
| `build_plot_50.py` | 50 `benchmark_semantic_<type>_NN.png` (axis, colorblind, legend) | `benchmark_semantic_gt.json` | Tables S6, S9 |
| `build_plot_20.py` | 20 `benchmark_combined_<type>_NN.png` (all six criteria) | `benchmark_combined_gt.json` | 100-query benchmark, rows 81–100 |

```bash
cd backend
venv/bin/python -m benchmarks.generators.build_plot      # -> uploads/image/benchmark_new_new/
venv/bin/python -m benchmarks.generators.build_plot_50   # -> uploads/image/benchmark_semantic_update/
venv/bin/python -m benchmarks.generators.build_plot_20   # -> uploads/image/benchmark_combined_20_new/
```

Provenance: the scripts came from the author's handover material. Comments
and printed text were translated to English, and directory creation moved
from import time into `main()`. Drawing code and parameters are unchanged:
the original and the committed scripts produce 120 byte-identical PNGs with
matplotlib 3.11.1.

`test_generators.py` pins the generators to the recorded data:

- `build_plot.py` reproduces the nominal DPI, font size and line width of all
  50 rows of `data/table12_13_measurements.csv`.
- `build_plot_20.py` agrees with the expected verdicts in
  `data/benchmark_100_ground_truth.csv` except in **2 cells**, which are not
  resolved yet:

  | Figure | Criterion | Generator | CSV |
  | :--- | :--- | :--- | :--- |
  | `benchmark_combined_volcano_07.png` | colorblind | PASS | FAIL |
  | `benchmark_combined_heatmap_11.png` | axis | PASS | FAIL |

  The author has to confirm which value the manuscript scored against. The
  test lists both cells exactly, so a correction or any new drift fails.

The semantic benchmark has no recorded per-figure verdicts in this repository,
so `build_plot_50.py` is checked only for its own structure (every criterion
has both verdicts, the heatmap legend is always PASS).

### 2. `data/ground_truth.jsonl` — one record per figure

⚠️ Not written yet. `figure_bench.py` reads this file, and the generators
write a different format (`benchmark_gt.json` keyed by file name, with
`expected_*` fields). A conversion from the generator output to the schema
below is still missing.

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

`generators/build_plot.py` generates all 50 figures as `PLOT_TYPES × PARAM_COMBOS`, and
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

---

## 100-query five-task benchmark: data only

`data/benchmark_100_ground_truth.csv` (UTF-8 with BOM, 100 rows) is the question
set behind manuscript Tables S1 and S10, with the result recorded for each
query. There is no runner for it in this directory.

| Rows | Task | Expected-answer columns |
| :--- | :--- | :--- |
| 1–20 | `direct` (greetings, capability questions) | `expected_intent` |
| 21–40 | `analysis` (peak-table analysis) | `expected_intent`; `input_file` names the peak table |
| 41–60 | `pubchem` (ID mapping) | `expected_cid`, `expected_inchikey` |
| 61–80 | `literature` (PubMedQA-style questions) | `expected_pmids` |
| 81–100 | plot review | `expected_axis`, `expected_colorblind`, `expected_legend`, `expected_dpi` (`PASS`/`FAIL`) |

`expected_intent` is empty for rows 81–100. Recorded results per row:
`tokens`, `total_cost`, `latency_sec`, `Is the task successful?`,
`Is the task completed?`. Questions are kept verbatim, most of them in Chinese.

The input files are **not** in this repository. Most analysis inputs are public
Metabolomics Workbench studies (`ST00xxxx_*`); `lcms_table.csv` is the
MetaboAnalyst example bundled in `backend/uploads/csv/`. The 20 plot-review
figures (`benchmark_combined_*.png`) are a separate set from the two 50-figure
benchmarks above, and they only have binary labels, so they cannot reproduce
the continuous font-size and line-width metrics. `generators/build_plot_20.py`
regenerates them (2 cells disagree with this CSV, see above).

The 20 analysis queries (rows 21–40) use peak tables whose features have no
metabolite names (m/z and retention time only). Pathway analysis (ORA and
GSEA) needs named metabolites, so it was skipped for all 20 queries, and the
recorded results do not include it. Confirmed by the author on 2026-10-27.
