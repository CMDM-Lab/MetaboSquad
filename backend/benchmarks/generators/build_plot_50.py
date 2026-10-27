"""Generate the 50-figure semantic-compliance benchmark (manuscript Tables S6, S9).

The figures test how well a vision LLM judges three semantic / layout
criteria:
  1. Axis titles & units present
  2. Colorblind-safe palette
  3. Legend legibility (legend does not cover data)

Unlike DPI, font size and line width, these criteria cannot be set by a
continuous value. Each figure therefore uses binary switches, which fix its
ground truth exactly:
  - axis_pass=True  → both axes carry meaningful labels (e.g. "log2(Fold Change)")
  - axis_pass=False → no axis labels at all
  - colorblind_pass=True  → blue/orange palette plus distinct marker shapes or line styles
  - colorblind_pass=False → red/green only, identical shapes and line styles (colour only)
  - legend_pass=True  → legend outside the axes, covering no data point
  - legend_pass=False → legend forced into the centre of the axes, over the data

A heatmap has no conventional legend, only a colour bar, so the legend
criterion is fixed to PASS for heatmaps (the colour bar does not usually
cover data). The axis and colorblind criteria still vary independently.

5 chart types × 10 (axis, colorblind, legend) combinations = 50 figures.

    cd backend && venv/bin/python -m benchmarks.generators.build_plot_50
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Output directory, relative to the working directory (run from backend/)
OUTPUT_DIR = Path("uploads/image/benchmark_semantic_update")

TARGET_WIDTH_MM = 85.0
TARGET_WIDTH_INCH = TARGET_WIDTH_MM / 25.4
ASPECT_RATIO = 4 / 3
TARGET_HEIGHT_INCH = TARGET_WIDTH_INCH / ASPECT_RATIO
FONT_PT = 9.0  # fixed at a compliant size, so physical properties do not interfere with this semantic test


# ─────────────────────────────────────────────────────────────────────────────
# Palette and legend helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_group_style(colorblind_pass: bool):
    """Return (colors, markers, linestyles).

    colorblind_pass=True  → blue/orange palette + distinct shapes/line styles (redundant encoding, readable with colour-vision deficiency)
    colorblind_pass=False → red/green palette + identical shapes/line styles (colour only, hard to read with colour-vision deficiency)
    """
    if colorblind_pass:
        colors = ["#0072B2", "#E69F00", "#009E73"]  # blue/orange/green (colorblind-safe palette)
        markers = ["o", "v", "^"]
        linestyles = ["-", "--", "-."]
    else:
        colors = ["red", "green", "red"]  # deliberately red/green only
        markers = ["o", "o", "o"]  # identical shapes, colour is the only cue
        linestyles = ["-", "-", "-"]
    return colors, markers, linestyles


def _place_legend(ax, legend_pass: bool, **legend_kwargs):
    """legend_pass=True moves the legend entirely outside the plotting area;
    False forces it over the centre of the data.

    Why: an earlier version used loc="upper left" for legend_pass=True. That
    only places the legend box at the upper-left corner inside the axes, and
    does not guarantee that the corner is free of data. A volcano plot fills
    almost the whole area, so the upper-left corner can still hide points.
    The only reliable way to avoid overlap is to move the legend outside the
    data coordinates with bbox_to_anchor (e.g. into the margin to the right
    of the axes), instead of betting on a corner that is usually empty.
    """
    if legend_pass:
        ax.legend(
            fontsize=FONT_PT,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),  # anchor outside the axes, on the right
            borderaxespad=0.0,
            **legend_kwargs,
        )
    else:
        # Force the legend into the centre, over the data points
        ax.legend(fontsize=FONT_PT, loc="center", framealpha=1.0, **legend_kwargs)


def _apply_axis_labels(ax, axis_pass: bool, xlabel: str, ylabel: str):
    """axis_pass=True sets meaningful labels; False leaves them blank."""
    if axis_pass:
        ax.set_xlabel(xlabel, fontsize=FONT_PT)
        ax.set_ylabel(ylabel, fontsize=FONT_PT)
    else:
        ax.set_xlabel("")
        ax.set_ylabel("")


# ─────────────────────────────────────────────────────────────────────────────
# Drawing functions, one per chart type
# ─────────────────────────────────────────────────────────────────────────────

def draw_pca(ax, axis_pass, colorblind_pass, legend_pass):
    np.random.seed(42)
    pca1_g1 = np.random.normal(loc=-2, scale=1, size=30)
    pca2_g1 = np.random.normal(loc=-1, scale=1, size=30)
    pca1_g2 = np.random.normal(loc=2, scale=1, size=30)
    pca2_g2 = np.random.normal(loc=1, scale=1, size=30)

    colors, markers, _ = _get_group_style(colorblind_pass)

    ax.scatter(pca1_g1, pca2_g1, c=colors[0], marker=markers[0], label="Group A", s=25)
    ax.scatter(pca1_g2, pca2_g2, c=colors[1], marker=markers[1], label="Group B", s=25)

    ax.set_title("PCA Score Plot", fontsize=FONT_PT)
    _apply_axis_labels(ax, axis_pass, "PC1 (45.2%)", "PC2 (18.7%)")
    _place_legend(ax, legend_pass)


def draw_volcano(ax, axis_pass, colorblind_pass, legend_pass):
    np.random.seed(101)
    n_genes = 200
    log2_fc = np.random.normal(0, 1.5, n_genes)
    p_val = np.random.exponential(0.1, n_genes)
    neg_log10_p = -np.log10(p_val + 1e-5)

    is_up = (log2_fc > 1) & (neg_log10_p > 1.3)
    is_down = (log2_fc < -1) & (neg_log10_p > 1.3)

    colors, markers, _ = _get_group_style(colorblind_pass)

    ax.scatter(
        log2_fc[~is_up & ~is_down], neg_log10_p[~is_up & ~is_down],
        c="gray", s=15, alpha=0.6, label="Not significant",
    )
    ax.scatter(log2_fc[is_up], neg_log10_p[is_up], c=colors[0], marker=markers[0], s=20, label="Up-regulated")
    ax.scatter(log2_fc[is_down], neg_log10_p[is_down], c=colors[1], marker=markers[1], s=20, label="Down-regulated")

    ax.axhline(y=1.3, color="black", linestyle="--", linewidth=1.5)

    ax.set_title("Volcano Plot", fontsize=FONT_PT)
    _apply_axis_labels(ax, axis_pass, "log2(Fold Change)", "-log10(p-value)")
    _place_legend(ax, legend_pass)


def draw_heatmap(fig, ax, axis_pass, colorblind_pass, legend_pass):
    """A heatmap has no conventional legend; legend_pass is fixed to PASS (see the module docstring)."""
    np.random.seed(202)
    data = np.random.rand(8, 8)

    # colorblind_pass=True uses viridis (a colorblind-safe sequential map)
    # colorblind_pass=False uses RdYlGn (red-yellow-green, a typical colorblind trap)
    cmap = "viridis" if colorblind_pass else "RdYlGn"
    cax = ax.matshow(data, cmap=cmap)
    fig.colorbar(cax, ax=ax, fraction=0.046, pad=0.04, label="Expression Level" if axis_pass else "")

    genes = [f"Gene_{i+1}" for i in range(8)]
    samples = [f"S_{i+1}" for i in range(8)]

    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    ax.set_xticklabels(samples, fontsize=FONT_PT, rotation=45)
    ax.set_yticklabels(genes, fontsize=FONT_PT)
    ax.set_title("Gene Expression Heatmap", fontsize=FONT_PT, pad=15)

    if not axis_pass:
        # A heatmap has no conventional x/y label; removing the tick labels
        # simulates "missing descriptive information"
        ax.set_xticklabels([])
        ax.set_yticklabels([])


def draw_boxplot(ax, axis_pass, colorblind_pass, legend_pass):
    np.random.seed(303)
    data = [np.random.normal(0, std, 30) for std in range(1, 4)]

    colors, _, _ = _get_group_style(colorblind_pass)
    box_colors = colors[:3] if colorblind_pass else ["red", "green", "red"]

    bp = ax.boxplot(data, patch_artist=True, widths=0.6, medianprops=dict(color="black", linewidth=2))
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)

    # Proxy legend handles that explain the group colours
    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=c, label=lbl) for c, lbl in zip(box_colors, ["Ctrl", "Treat_A", "Treat_B"])]

    ax.set_title("Distribution Boxplot", fontsize=FONT_PT)
    ax.set_xticklabels(["Ctrl", "Treat_A", "Treat_B"], fontsize=FONT_PT)
    _apply_axis_labels(ax, axis_pass, "Group", "Expression Level")

    if legend_pass:
        ax.legend(
            handles=handles, fontsize=FONT_PT, loc="upper left",
            bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0,
        )
    else:
        ax.legend(handles=handles, fontsize=FONT_PT, loc="center", framealpha=1.0)


def draw_bar_error(ax, axis_pass, colorblind_pass, legend_pass):
    np.random.seed(404)
    groups = ["Ctrl", "Treat_A", "Treat_B", "Treat_C"]
    means = np.array([1.0, 1.8, 0.6, 2.3])
    errors = np.array([0.15, 0.25, 0.1, 0.3])
    x = np.arange(len(groups))

    if colorblind_pass:
        bar_colors = ["#0072B2", "#E69F00", "#009E73", "#D55E00"]
        hatches = ["", "//", "xx", ".."]  # hatching as an extra cue, not colour alone
    else:
        bar_colors = ["red", "green", "red", "green"]
        hatches = ["", "", "", ""]

    bars = []
    for i in range(len(groups)):
        b = ax.bar(
            x[i], means[i], yerr=errors[i], capsize=5,
            color=bar_colors[i], hatch=hatches[i],
            edgecolor="black", linewidth=1.5, label=groups[i],
        )
        bars.append(b)

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=FONT_PT)
    ax.set_title("Metabolite Abundance by Group", fontsize=FONT_PT)
    _apply_axis_labels(ax, axis_pass, "Group", "Relative Metabolite Level")
    _place_legend(ax, legend_pass)


# ─────────────────────────────────────────────────────────────────────────────
# 10 (axis_pass, colorblind_pass, legend_pass) combinations
# ─────────────────────────────────────────────────────────────────────────────
#
# All 8 base permutations (2^3) are covered, plus 2 repeated extreme cases
# (all PASS / all FAIL), so that each criterion has enough independent
# positive and negative samples across the 50 figures.
SEMANTIC_COMBOS = [
    # (axis_pass, colorblind_pass, legend_pass, note)
    (True,  True,  True,  "all compliant"),
    (False, False, False, "all non-compliant"),
    (True,  False, True,  "axis labels OK / palette unsafe / legend OK"),
    (True,  True,  False, "axis labels OK / palette safe / legend covers data"),
    (False, True,  True,  "axis labels missing / palette safe / legend OK"),
    (False, False, True,  "axis labels missing / palette unsafe / legend OK"),
    (True,  False, False, "axis labels OK / palette unsafe / legend covers data"),
    (False, True,  False, "axis labels missing / palette safe / legend covers data"),
    (True,  True,  True,  "all compliant (repeated sample, adds sample size)"),
    (False, False, False, "all non-compliant (repeated sample, adds sample size)"),
]

PLOT_TYPES = ["pca", "volcano", "heatmap", "boxplot", "bar_error"]


def build_test_configs() -> list[dict]:
    configs = []
    for plot_type in PLOT_TYPES:
        for idx, (axis_pass, colorblind_pass, legend_pass, note) in enumerate(SEMANTIC_COMBOS, start=1):
            configs.append({
                "type": plot_type,
                "axis_pass": axis_pass,
                "colorblind_pass": colorblind_pass,
                "legend_pass": legend_pass,
                "note": note,
                "name": f"benchmark_semantic_{plot_type}_{idx:02d}.png",
            })
    return configs


def main(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)
    test_configs = build_test_configs()
    ground_truth_db = {}

    for config in test_configs:
        fig, ax = plt.subplots(figsize=(TARGET_WIDTH_INCH, TARGET_HEIGHT_INCH))

        plot_type = config["type"]
        axis_pass = config["axis_pass"]
        colorblind_pass = config["colorblind_pass"]
        legend_pass = config["legend_pass"]
        filename = config["name"]
        img_path = output_dir / filename

        # A heatmap has no conventional legend; the legend criterion is fixed to PASS
        effective_legend_pass = legend_pass
        if plot_type == "heatmap":
            effective_legend_pass = True  # fixed, see the module docstring

        if plot_type == "pca":
            draw_pca(ax, axis_pass, colorblind_pass, legend_pass)
        elif plot_type == "volcano":
            draw_volcano(ax, axis_pass, colorblind_pass, legend_pass)
        elif plot_type == "heatmap":
            draw_heatmap(fig, ax, axis_pass, colorblind_pass, legend_pass)
        elif plot_type == "boxplot":
            draw_boxplot(ax, axis_pass, colorblind_pass, legend_pass)
        elif plot_type == "bar_error":
            draw_bar_error(ax, axis_pass, colorblind_pass, legend_pass)
        else:
            plt.close(fig)
            raise ValueError(f"Unknown chart type: {plot_type}")

        # With legend_pass=True the legend sits outside the axes (see
        # _place_legend), so bbox_inches="tight" is required to keep that area
        # in the saved image; otherwise the legend is cropped away. This
        # benchmark tests semantic criteria only, not physical properties
        # (DPI/font/line width), so the canvas-size change from
        # bbox_inches="tight" does not affect it.
        plt.savefig(img_path, dpi=300, bbox_inches="tight")
        plt.close(fig)

        ground_truth_db[filename] = {
            "image_path": str(img_path),
            "plot_type": plot_type,
            "note": config["note"],
            "expected_axis_pass": "PASS" if axis_pass else "FAIL",
            "expected_colorblind_pass": "PASS" if colorblind_pass else "FAIL",
            "expected_legend_pass": "PASS" if effective_legend_pass else "FAIL",
        }

    gt_file_path = output_dir / "benchmark_semantic_gt.json"
    with open(gt_file_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth_db, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(test_configs)} semantic benchmark figures")
    print(f"  ({len(PLOT_TYPES)} chart types × {len(SEMANTIC_COMBOS)} semantic combinations)")
    print(f"Figures and ground truth saved to: {output_dir.resolve()}")

    print("\n=== Ground truth PASS/FAIL distribution ===")
    for criterion_key, label in [
        ("expected_axis_pass", "Axis titles & units"),
        ("expected_colorblind_pass", "Colorblind-safe palette"),
        ("expected_legend_pass", "Legend legibility"),
    ]:
        pass_count = sum(1 for v in ground_truth_db.values() if v[criterion_key] == "PASS")
        fail_count = len(ground_truth_db) - pass_count
        print(f"[{label}] PASS={pass_count} / FAIL={fail_count}")


if __name__ == "__main__":
    main()
