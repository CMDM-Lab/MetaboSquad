"""Generate the 20 plot-review figures of the 100-query benchmark (rows 81–100).

5 chart types × 4 multi-criterion conditions. The figures test how well a
vision LLM or an automated figure checker judges six criteria:

Semantic / layout criteria
  1. Axis titles & units present: axis_pass (True/False)
  2. Colorblind-safe palette: colorblind_pass (True/False)
  3. Legend legibility: legend_pass (True/False; covers both "legend covers
     data" and "legend missing")

Physical / format criteria
  4. Font size >= 8 pt: font_pt (threshold 8.0)
  5. Line width >= 2 pt: line_pt (threshold 2.0)
  6. Image DPI >= 300: dpi (threshold 300)

⚠️ Two figures disagree with the expected values recorded in
`../data/benchmark_100_ground_truth.csv`; see the benchmarks README.

    cd backend && venv/bin/python -m benchmarks.generators.build_plot_20
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Output directory, relative to the working directory (run from backend/)
OUTPUT_DIR = Path("uploads/image/benchmark_combined_20_new")

TARGET_WIDTH_MM = 85.0
TARGET_WIDTH_INCH = TARGET_WIDTH_MM / 25.4
ASPECT_RATIO = 4 / 3
TARGET_HEIGHT_INCH = TARGET_WIDTH_INCH / ASPECT_RATIO

# PASS thresholds
FONT_THRESHOLD = 8.0
LINE_THRESHOLD = 2.0
DPI_THRESHOLD = 300


# ─────────────────────────────────────────────────────────────────────────────
# Helpers and drawing functions
# ─────────────────────────────────────────────────────────────────────────────

def _get_group_style(colorblind_pass: bool):
    """Return (colors, markers, linestyles)."""
    if colorblind_pass:
        colors = ["#0072B2", "#B38B2B", "#009E73"]  # blue/orange/green (colorblind-safe palette)
        markers = ["o", "v", "^"]
        linestyles = ["-", "--", "-."]
    else:
        colors = ["#15FF0D", "red", "#15FF0D"]  # deliberately red/green as the only cue
        markers = ["o", "o", "o"]
        linestyles = ["-", "-", "-"]
    return colors, markers, linestyles


def _place_legend(ax, legend_mode: str, font_pt: float, **legend_kwargs):
    """Legend display mode:
    - 'ok': legend outside the axes (PASS)
    - 'obscured': legend over the centre, covering data (FAIL)
    - 'missing': no legend at all (FAIL)
    """
    if legend_mode == "ok":
        ax.legend(
            fontsize=font_pt,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0.0,
            **legend_kwargs,
        )
    elif legend_mode == "obscured":
        # Force the legend into the centre, over the data points
        ax.legend(fontsize=font_pt, loc="center", framealpha=1.0, **legend_kwargs)
    elif legend_mode == "missing":
        # Do not call ax.legend() at all, so no legend appears
        pass


def _apply_axis_labels(ax, axis_pass: bool, xlabel: str, ylabel: str, font_pt: float):
    """Apply the axis labels and their font size."""
    if axis_pass:
        ax.set_xlabel(xlabel, fontsize=font_pt)
        ax.set_ylabel(ylabel, fontsize=font_pt)
    else:
        ax.set_xlabel("")
        ax.set_ylabel("")


# ─────────────────────────────────────────────────────────────────────────────
# Drawing functions, one per chart type
# ─────────────────────────────────────────────────────────────────────────────

def draw_pca(ax, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt):
    np.random.seed(42)
    pca1_g1 = np.random.normal(loc=-2, scale=1, size=30)
    pca2_g1 = np.random.normal(loc=-1, scale=1, size=30)
    pca1_g2 = np.random.normal(loc=2, scale=1, size=30)
    pca2_g2 = np.random.normal(loc=1, scale=1, size=30)

    colors, markers, _ = _get_group_style(colorblind_pass)

    ax.scatter(pca1_g1, pca2_g1, c=colors[0], marker=markers[0], label="Group A", s=25, linewidths=line_pt)
    ax.scatter(pca1_g2, pca2_g2, c=colors[1], marker=markers[1], label="Group B", s=25, linewidths=line_pt)

    ax.set_title("PCA Score Plot", fontsize=font_pt)
    ax.tick_params(axis="both", labelsize=font_pt)
    _apply_axis_labels(ax, axis_pass, "PC1 (45.2%)", "PC2 (18.7%)", font_pt)
    _place_legend(ax, legend_mode, font_pt)


def draw_volcano(ax, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt):
    np.random.seed(101)
    n_genes = 200
    log2_fc = np.random.normal(0, 1.5, n_genes)
    p_val = np.random.exponential(0.1, n_genes)
    neg_log10_p = -np.log10(p_val + 1e-5)

    is_up = (log2_fc > 1) & (neg_log10_p > 1.3)
    is_down = (log2_fc < -1) & (neg_log10_p > 1.3)

    colors, markers, _ = _get_group_style(colorblind_pass)

    ax.scatter(log2_fc[~is_up & ~is_down], neg_log10_p[~is_up & ~is_down], c="gray", s=15, alpha=0.6, label="Not sig")
    ax.scatter(log2_fc[is_up], neg_log10_p[is_up], c=colors[0], marker=markers[0], s=20, label="Up")
    ax.scatter(log2_fc[is_down], neg_log10_p[is_down], c=colors[1], marker=markers[1], s=20, label="Down")

    ax.axhline(y=1.3, color="black", linestyle="--", linewidth=line_pt)

    ax.set_title("Volcano Plot", fontsize=font_pt)
    ax.tick_params(axis="both", labelsize=font_pt)
    _apply_axis_labels(ax, axis_pass, "log2(Fold Change)", "-log10(p-value)", font_pt)
    _place_legend(ax, legend_mode, font_pt)


def draw_heatmap(fig, ax, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt):
    np.random.seed(202)
    data = np.random.rand(8, 8)

    cmap = "viridis" if colorblind_pass else "RdYlGn"
    cax = ax.matshow(data, cmap=cmap)

    cbar = fig.colorbar(cax, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=font_pt)
    if axis_pass:
        cbar.set_label("Expression Level", fontsize=font_pt)

    genes = [f"Gene_{i+1}" for i in range(8)]
    samples = [f"S_{i+1}" for i in range(8)]

    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    ax.set_xticklabels(samples, fontsize=font_pt, rotation=45)
    ax.set_yticklabels(genes, fontsize=font_pt)
    ax.set_title("Gene Expression Heatmap", fontsize=font_pt, pad=15)

    if not axis_pass:
        ax.set_xticklabels([])
        ax.set_yticklabels([])


def draw_boxplot(ax, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt):
    np.random.seed(303)
    data = [np.random.normal(0, std, 30) for std in range(1, 4)]

    colors, _, _ = _get_group_style(colorblind_pass)
    box_colors = colors[:3] if colorblind_pass else ["red", "green", "red"]

    bp = ax.boxplot(
        data,
        patch_artist=True,
        widths=0.6,
        boxprops=dict(linewidth=line_pt),
        whiskerprops=dict(linewidth=line_pt),
        capprops=dict(linewidth=line_pt),
        medianprops=dict(color="black", linewidth=line_pt),
    )
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)

    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=c, label=lbl) for c, lbl in zip(box_colors, ["Ctrl", "Treat_A", "Treat_B"])]

    ax.set_title("Distribution Boxplot", fontsize=font_pt)
    ax.set_xticklabels(["Ctrl", "Treat_A", "Treat_B"], fontsize=font_pt)
    ax.tick_params(axis="both", labelsize=font_pt)
    _apply_axis_labels(ax, axis_pass, "Group", "Expression Level", font_pt)

    if legend_mode == "ok":
        ax.legend(handles=handles, fontsize=font_pt, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
    elif legend_mode == "obscured":
        ax.legend(handles=handles, fontsize=font_pt, loc="center", framealpha=1.0)
    elif legend_mode == "missing":
        pass


def draw_bar_error(ax, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt):
    np.random.seed(404)
    groups = ["Ctrl", "Treat_A", "Treat_B", "Treat_C"]
    means = np.array([1.0, 1.8, 0.6, 2.3])
    errors = np.array([0.15, 0.25, 0.1, 0.3])
    x = np.arange(len(groups))

    if colorblind_pass:
        bar_colors = ["#0072B2", "#E69F00", "#009E73", "#D55E00"]
        hatches = ["", "//", "xx", ".."]
    else:
        bar_colors = ["red", "green", "red", "green"]
        hatches = ["", "", "", ""]

    for i in range(len(groups)):
        ax.bar(
            x[i],
            means[i],
            yerr=errors[i],
            capsize=5,
            color=bar_colors[i],
            hatch=hatches[i],
            edgecolor="black",
            linewidth=line_pt,
            error_kw=dict(elinewidth=line_pt, capthick=line_pt),
            label=groups[i],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=font_pt)
    ax.tick_params(axis="both", labelsize=font_pt)
    ax.set_title("Metabolite Abundance", fontsize=font_pt)
    _apply_axis_labels(ax, axis_pass, "Group", "Relative Abundance", font_pt)
    _place_legend(ax, legend_mode, font_pt)


# ─────────────────────────────────────────────────────────────────────────────
# 20 test cases (legend_mode is one of "ok", "obscured", "missing")
# ─────────────────────────────────────────────────────────────────────────────

COMBINED_TEST_CASES = [
    # (plot_type, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt, dpi, note)
    # PCA (4 figures)
    ("pca", True, True, "ok", 10.0, 3.0, 400, "all PASS"),
    ("pca", False, False, "missing", 6.0, 1.0, 200, "all FAIL (legend missing)"),
    ("pca", True, False, "ok", 7.0, 2.5, 400, "colorblind and font FAIL"),
    ("pca", False, True, "obscured", 9.0, 1.5, 200, "axis, legend covers data, line, DPI FAIL"),

    # Volcano plot (4 figures)
    ("volcano", True, True, "ok", 9.0, 2.5, 350, "all PASS"),
    ("volcano", False, False, "obscured", 7.0, 1.5, 250, "all FAIL (legend covers data)"),
    ("volcano", True, True, "missing", 6.0, 3.0, 250, "legend missing, font and DPI FAIL"),
    ("volcano", False, True, "ok", 10.0, 1.0, 400, "axis missing and line FAIL"),

    # Heatmap (4 figures) - no conventional legend, legend_mode is always treated as "ok"
    ("heatmap", True, True, "ok", 10.0, 2.5, 300, "all PASS"),
    ("heatmap", False, False, "ok", 6.0, 1.0, 200, "all FAIL (legend not varied)"),
    ("heatmap", True, False, "ok", 9.0, 3.0, 250, "palette unsafe and DPI FAIL"),
    ("heatmap", False, True, "ok", 7.0, 2.0, 400, "tick labels missing and font FAIL"),

    # Boxplot (4 figures)
    ("boxplot", True, True, "ok", 8.0, 2.0, 300, "all PASS (at the threshold)"),
    ("boxplot", False, False, "missing", 6.0, 1.0, 200, "all FAIL (legend missing)"),
    ("boxplot", True, False, "obscured", 10.0, 1.2, 350, "palette unsafe, legend covers data, line FAIL"),
    ("boxplot", False, True, "ok", 7.5, 2.5, 220, "axis labels missing, font and DPI FAIL"),

    # Bar with error bars (4 figures)
    ("bar_error", True, True, "ok", 10.0, 3.0, 400, "all PASS"),
    ("bar_error", False, False, "obscured", 6.0, 1.0, 200, "all FAIL (legend covers data)"),
    ("bar_error", True, True, "missing", 9.0, 1.8, 320, "legend missing and line FAIL"),
    ("bar_error", False, False, "ok", 7.8, 2.2, 400, "axis labels, palette, font FAIL"),
]


def main(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_db = {}

    for idx, case in enumerate(COMBINED_TEST_CASES, start=1):
        (plot_type, axis_pass, colorblind_pass, legend_mode, font_pt, line_pt, dpi, note) = case
        filename = f"benchmark_combined_{plot_type}_{idx:02d}.png"
        img_path = output_dir / filename

        fig, ax = plt.subplots(figsize=(TARGET_WIDTH_INCH, TARGET_HEIGHT_INCH))

        # A heatmap has no conventional legend; legend is always ok (PASS)
        effective_legend_mode = "ok" if plot_type == "heatmap" else legend_mode
        legend_pass = (effective_legend_mode == "ok")

        # Draw the chart
        if plot_type == "pca":
            draw_pca(ax, axis_pass, colorblind_pass, effective_legend_mode, font_pt, line_pt)
        elif plot_type == "volcano":
            draw_volcano(ax, axis_pass, colorblind_pass, effective_legend_mode, font_pt, line_pt)
        elif plot_type == "heatmap":
            draw_heatmap(fig, ax, axis_pass, colorblind_pass, effective_legend_mode, font_pt, line_pt)
        elif plot_type == "boxplot":
            draw_boxplot(ax, axis_pass, colorblind_pass, effective_legend_mode, font_pt, line_pt)
        elif plot_type == "bar_error":
            draw_bar_error(ax, axis_pass, colorblind_pass, effective_legend_mode, font_pt, line_pt)

        # Save with the target DPI
        plt.savefig(img_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)

        # Record the ground truth
        ground_truth_db[filename] = {
            "image_path": str(img_path),
            "plot_type": plot_type,
            "note": note,
            "parameters": {
                "font_pt": font_pt,
                "line_pt": line_pt,
                "dpi": dpi,
                "legend_mode": effective_legend_mode,  # also record the legend mode (ok / obscured / missing)
            },
            "expected_axis_pass": "PASS" if axis_pass else "FAIL",
            "expected_colorblind_pass": "PASS" if colorblind_pass else "FAIL",
            "expected_legend_pass": "PASS" if legend_pass else "FAIL",
            "expected_font_pass": "PASS" if font_pt >= FONT_THRESHOLD else "FAIL",
            "expected_line_pass": "PASS" if line_pt >= LINE_THRESHOLD else "FAIL",
            "expected_dpi_pass": "PASS" if dpi >= DPI_THRESHOLD else "FAIL",
        }

    # Write the JSON
    gt_file_path = output_dir / "benchmark_combined_gt.json"
    with open(gt_file_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth_db, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(COMBINED_TEST_CASES)} combined benchmark figures")
    print(f"Figures and ground truth saved to: {output_dir.resolve()}\n")

    print("=== PASS / FAIL count per criterion ===")
    criteria = [
        ("expected_axis_pass", "Axis titles & units"),
        ("expected_colorblind_pass", "Colorblind-safe palette"),
        ("expected_legend_pass", "Legend legibility and presence"),
        ("expected_font_pass", f"Font size >= {FONT_THRESHOLD} pt"),
        ("expected_line_pass", f"Line width >= {LINE_THRESHOLD} pt"),
        ("expected_dpi_pass", f"Image resolution >= {DPI_THRESHOLD} DPI"),
    ]

    for key, label in criteria:
        pass_count = sum(1 for v in ground_truth_db.values() if v[key] == "PASS")
        fail_count = len(ground_truth_db) - pass_count
        print(f"[{label}] PASS={pass_count} / FAIL={fail_count}")


if __name__ == "__main__":
    main()
