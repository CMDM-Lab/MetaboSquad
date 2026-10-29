# Benchmarks

This directory holds the evaluation datasets used in the manuscript, the
programs that generate them, and the code that scores the results.

| Dataset | Size | What it evaluates | Source |
| :--- | :--- | :--- | :--- |
| Boundary benchmark | 50 figures | DPI, font size and line width, measured as continuous values | `generators/build_plot.py` |
| Semantic-compliance benchmark | 50 figures | Axis titles and units, colorblind-safe palette, legend legibility | `generators/build_plot_50.py` |
| 100-query task benchmark | 100 queries in 5 task categories | Intent routing, task completion and task success | `data/benchmark_100_ground_truth.csv`; the 20 plot-review figures come from `generators/build_plot_20.py` |

All commands below run from `backend/` with `venv/bin/python`.

## Figure benchmarks

### Generating the figures

Each generator writes the PNG files and a ground-truth JSON file. The ground
truth is the set of parameters that each figure was drawn with.

| Generator | Figures | Ground-truth file |
| :--- | :--- | :--- |
| `build_plot.py` | 50 `benchmark_<type>_NN.png` | `benchmark_gt.json` |
| `build_plot_50.py` | 50 `benchmark_semantic_<type>_NN.png` | `benchmark_semantic_gt.json` |
| `build_plot_20.py` | 20 `benchmark_combined_<type>_NN.png` | `benchmark_combined_gt.json` |

```bash
venv/bin/python -m benchmarks.generators.build_plot      # -> uploads/image/benchmark_new_new/
venv/bin/python -m benchmarks.generators.build_plot_50   # -> uploads/image/benchmark_semantic_update/
venv/bin/python -m benchmarks.generators.build_plot_20   # -> uploads/image/benchmark_combined_20_new/
```

All three use the same five chart types: PCA score plot, volcano plot,
heatmap, box plot and bar chart with error bars.

- **Boundary benchmark.** 5 chart types × 10 combinations of font size
  (6–10 pt), line width (1–3 pt) and resolution (200–400 dpi). The PASS
  thresholds are 8 pt, 2 pt and 300 dpi. The combinations include values
  exactly at each threshold, and the three criteria vary independently.
- **Semantic-compliance benchmark.** 5 chart types × 10 combinations of the
  three criteria, which covers all 8 PASS/FAIL permutations plus repeated
  all-PASS and all-FAIL cases. A heatmap has a colour bar instead of a legend,
  so its legend criterion is always PASS.
- **Plot-review figures of the task benchmark.** 20 figures that combine all
  six criteria. A legend can be correct, cover the data, or be missing.

`test_generators.py` checks that `build_plot.py` reproduces the nominal values
in `data/table12_13_measurements.csv`, and that `build_plot_20.py` reproduces
the expected verdicts in rows 81–100 of `data/benchmark_100_ground_truth.csv`.

### Measurement accuracy (boundary benchmark)

`data/table12_13_measurements.csv` has one row per boundary figure: the
nominal DPI, font size and line width, and the values the system measured.
`table12_13.py` computes the measurement accuracy from it: MAE, MAPE, RMSE and
Pearson r, overall and per chart type. `test_table12_13.py` pins every
published value.

```bash
venv/bin/python -m benchmarks.table12_13
```

Definitions:

- Font-size error is `|measured_font_pt − nominal_font_pt|`.
- Line-width error is `|median_line_pt − nominal_line_pt|`. It uses the median
  estimate, not `estimated_line_pt`. The two are identical for 41 of 50
  figures and differ mainly on heatmaps (e.g. `benchmark_heatmap_03`:
  nominal 2.0, median 2.06, estimated 6.25).
- MAPE is the error divided by the nominal value.

`data/line_width_formulas_2026-08-28.xlsx` contains the same line-width
calculation as a spreadsheet.

The PCA, volcano and box-plot figures have identical line-width measurements.
This is by construction: `build_plot.py` gives every chart type the same
line-width sequence (3, 1, 2, 1.5, 2.5, 2.5, 1.5, 1, 3, 2), and these three
chart types consist mostly of strokes. Heatmaps (colour fills) and bar charts
(filled rectangles) have different line features, so their measurements
differ. The same nominal font sizes give different measured values across
chart types, because the OCR-based estimator reacts to everything else on the
canvas.

### Running the figure review

`figure_bench.py` sends each figure to the plot-review agent and scores the
verdicts. Each run writes `runs/<timestamp>/` with the git SHA, the model,
the execution path and the raw output per figure.

```bash
# through the supervisor graph, with intent routing
venv/bin/python -m benchmarks.figure_bench run --path agent

# the plot-review subgraph directly
venv/bin/python -m benchmarks.figure_bench run --path node

# another model
venv/bin/python -m benchmarks.figure_bench run --path node --model gpt-5.4-mini

# paired comparison of two runs
venv/bin/python -m benchmarks.figure_bench compare runs/<a> runs/<b>
```

`--path agent` invokes the compiled graph with an in-memory checkpointer, so
it needs neither a running server nor the database. `compare` reports
per-criterion precision, recall and F1, McNemar's test on the paired binary
decisions, and the Friedman test across chart types for the continuous
metrics.

Scoring rules:

- Font size is taken from `text_report.min_pt`, the smallest text in the
  figure. `avg_pt` is recorded as well.
- Line width is taken from `line_analysis.estimated_true_line_pt`.
  `median_width_pt` is recorded as well.
- If the parser cannot read a verdict, the verdict is left absent and is not
  scored. It is never given a default value.

The runner reads `data/ground_truth.jsonl`, one record per figure:

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

`chart_type` ∈ `pca_score | volcano | heatmap | box | bar`. `font_size_pt` and
`line_width_pt` are the true values that the continuous metrics are computed
against. This file is not included: build it from the generators'
ground-truth JSON.

## 100-query task benchmark

`data/benchmark_100_ground_truth.csv` (UTF-8 with BOM) holds the 100 queries,
the expected answers and the recorded result of each query.

| Rows | Task | Expected-answer columns |
| :--- | :--- | :--- |
| 1–20 | `direct` (greetings, capability questions) | `expected_intent` |
| 21–40 | `analysis` (peak-table analysis) | `expected_intent`; `input_file` names the peak table |
| 41–60 | `pubchem` (ID mapping) | `expected_cid`, `expected_inchikey` |
| 61–80 | `literature` (PubMedQA-style questions) | `expected_pmids` |
| 81–100 | plot review | `expected_axis`, `expected_colorblind`, `expected_legend`, `expected_dpi` (`PASS`/`FAIL`) |

Recorded results per row: `tokens`, `total_cost`, `latency_sec`,
`Is the task successful?` and `Is the task completed?`. The queries are
verbatim, most of them in Chinese. There is no runner for this benchmark in
this directory.

Input files for the analysis queries are not included. They come from:

- `ST00xxxx_*`: public studies in [Metabolomics Workbench](https://www.metabolomicsworkbench.org/).
- `A1_pos.csv`, `B1_pos.csv`, `C1_pos.csv`, `malaria_feature_table.csv`:
  MetaboAnalyst example files, listed on the
  [MetaboAnalyst data format page](https://www.metaboanalyst.ca/docs/Format.xhtml).
- `lcms_table.csv`: the MetaboAnalyst example in `backend/uploads/csv/`.

The plot-review figures (`benchmark_combined_*.png`) are generated by
`generators/build_plot_20.py`. They carry PASS/FAIL labels only, so they are
not used for the continuous font-size and line-width metrics.

Pathway analysis (ORA and GSEA) maps metabolite names to KEGG IDs. If the
significant features are m/z values (feature names made only of m/z and
retention-time numbers, e.g. `327.2/3418`) instead of metabolite names, the
system skips pathway analysis. This is expected behaviour, not a failure: the
report states `Automatically skip ORA and GSEA analysis`, and the task
continues. A failure reads `⚠️ Pathway analysis failed` instead. The 20
analysis queries all use peak tables with m/z features only, so pathway
analysis was skipped for each of them.

### Single-agent baseline

The controller comparison uses one agent in place of the supervisor graph:
`src/graph_agent/baseline/single_agent.py`. It gets the graph's tools, a
system prompt that names the task types, and one guide tool per file in
`src/graph_agent/baseline/skills/`. The agent calls a guide tool to read the
workflow of a task before it starts the task. This is the setting of the
benchmark run. The mean tool calls in the manuscript's Table 2 count task-tool
calls only, not guide-tool calls. `with_skills=False` removes the guide tools.
The prompts and guides are verbatim, some of them in Chinese. From `backend/`:

```bash
venv/bin/python -c 'from src.graph_agent.baseline.single_agent import run; run("Look up the PubChem CID and InChIKey of tryptophan")'
```

## Environment

The same as the application: `OPENAI_API_KEY`, the `meta_image:v3` R
container, and `mummichog` in the virtual environment. Use `venv/bin/python`.

```bash
venv/bin/python -m pytest benchmarks/ -q
```
