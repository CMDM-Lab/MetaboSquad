"""Generate the 50-figure boundary benchmark (manuscript Tables S5, S7, S8).

Five chart types x ten (font_pt, line_pt, dpi) combinations. The ground truth
is the generator's own parameters, written to `benchmark_gt.json` next to the
images. The nominal values match `../data/table12_13_measurements.csv`
figure for figure (pinned by `test_generators.py`).

    cd backend && venv/bin/python -m benchmarks.generators.build_plot
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

# Output directory, relative to the working directory (run from backend/)
OUTPUT_DIR = Path("uploads/image/benchmark_new_new")

# Physical settings shared by every figure
TARGET_WIDTH_MM = 85.0  # single-column width, 85 mm
TARGET_WIDTH_INCH = TARGET_WIDTH_MM / 25.4  # about 3.3465 in
ASPECT_RATIO = 4 / 3
TARGET_HEIGHT_INCH = TARGET_WIDTH_INCH / ASPECT_RATIO


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers, one per chart type
# ─────────────────────────────────────────────────────────────────────────────

def draw_pca(ax, font_pt, line_pt):
    """PCA score plot"""
    np.random.seed(42)
    pca1_g1 = np.random.normal(loc=-2, scale=1, size=30)
    pca2_g1 = np.random.normal(loc=-1, scale=1, size=30)
    pca1_g2 = np.random.normal(loc=2, scale=1, size=30)
    pca2_g2 = np.random.normal(loc=1, scale=1, size=30)

    ax.scatter(pca1_g1, pca2_g1, c="crimson", label="Group A", s=25)
    ax.scatter(pca1_g2, pca2_g2, c="dodgerblue", label="Group B", s=25)

    e1 = Ellipse((-2, -1), width=4, height=3, angle=15, edgecolor="crimson", fc="none", lw=line_pt)
    e2 = Ellipse((2, 1), width=4, height=3, angle=-15, edgecolor="dodgerblue", fc="none", lw=line_pt)
    ax.add_patch(e1)
    ax.add_patch(e2)

    ax.set_title("PCA Score Plot", fontsize=font_pt)
    ax.set_xlabel("PC1 (45.2%)", fontsize=font_pt)
    ax.set_ylabel("PC2 (18.7%)", fontsize=font_pt)
    ax.legend(fontsize=font_pt, loc="upper left")


def draw_volcano(ax, font_pt, line_pt):
    """Volcano plot"""
    np.random.seed(101)
    n_genes = 200
    log2_fc = np.random.normal(0, 1.5, n_genes)
    p_val = np.random.exponential(0.1, n_genes)
    neg_log10_p = -np.log10(p_val + 1e-5)

    is_up = (log2_fc > 1) & (neg_log10_p > 1.3)
    is_down = (log2_fc < -1) & (neg_log10_p > 1.3)

    ax.scatter(log2_fc[~is_up & ~is_down], neg_log10_p[~is_up & ~is_down], c="gray", s=15, alpha=0.6)
    ax.scatter(log2_fc[is_up], neg_log10_p[is_up], c="red", s=20)
    ax.scatter(log2_fc[is_down], neg_log10_p[is_down], c="blue", s=20)

    ax.axhline(y=1.3, color="black", linestyle="--", linewidth=line_pt)
    ax.axvline(x=1, color="black", linestyle="--", linewidth=line_pt)
    ax.axvline(x=-1, color="black", linestyle="--", linewidth=line_pt)

    ax.set_title("Volcano Plot", fontsize=font_pt)
    ax.set_xlabel("log2(Fold Change)", fontsize=font_pt)
    ax.set_ylabel("-log10(p-value)", fontsize=font_pt)


def draw_heatmap(fig, ax, font_pt, line_pt):
    """Heatmap. line_pt sets the frame around the cells, to test whether
    filled cells interfere with the line-width measurement."""
    np.random.seed(202)
    data = np.random.rand(8, 8)
    cax = ax.matshow(data, cmap="viridis")

    # Draw the frame with line_pt: tests whether a thin line next to filled
    # regions is misread
    for spine in ax.spines.values():
        spine.set_linewidth(line_pt)

    fig.colorbar(cax, ax=ax, fraction=0.046, pad=0.04)

    genes = [f"Gene_{i+1}" for i in range(8)]
    samples = [f"S_{i+1}" for i in range(8)]

    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    ax.set_xticklabels(samples, fontsize=font_pt, rotation=45)
    ax.set_yticklabels(genes, fontsize=font_pt)
    ax.set_title("Gene Expression Heatmap", fontsize=font_pt, pad=15)


def draw_boxplot(ax, font_pt, line_pt):
    """Box plot"""
    np.random.seed(303)
    data = [np.random.normal(0, std, 30) for std in range(1, 4)]

    ax.boxplot(
        data,
        patch_artist=True,
        boxprops=dict(linewidth=line_pt, facecolor="whitesmoke"),
        whiskerprops=dict(linewidth=line_pt),
        capprops=dict(linewidth=line_pt),
        medianprops=dict(linewidth=line_pt, color="firebrick"),
    )

    ax.set_title("Distribution Boxplot", fontsize=font_pt)
    ax.set_xticklabels(["Ctrl", "Treat_A", "Treat_B"], fontsize=font_pt)
    ax.set_ylabel("Expression Level", fontsize=font_pt)


def draw_bar_error(ax, font_pt, line_pt):
    """Bar chart with error bars.

    A common form in metabolomics papers (e.g. comparing one metabolite's
    level across groups). Error bars are usually thinner than the bar edges,
    which makes them a good robustness test for line-width measurement: a
    system that only picks up the thickest line misses the thin error bars.
    The error bars deliberately share line_pt with the bar edges so that
    both enter the measurement.
    """
    np.random.seed(404)
    groups = ["Ctrl", "Treat_A", "Treat_B", "Treat_C"]
    means = np.array([1.0, 1.8, 0.6, 2.3])
    errors = np.array([0.15, 0.25, 0.1, 0.3])

    x = np.arange(len(groups))
    bars = ax.bar(
        x, means, yerr=errors, capsize=5,
        color=["lightgray", "salmon", "skyblue", "mediumseagreen"],
        edgecolor="black", linewidth=line_pt,
        error_kw={"elinewidth": line_pt, "capthick": line_pt},
    )

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=font_pt)
    ax.set_ylabel("Relative Metabolite Level", fontsize=font_pt)
    ax.set_title("Metabolite Abundance by Group", fontsize=font_pt)
    ax.tick_params(axis="y", labelsize=font_pt)


# ─────────────────────────────────────────────────────────────────────────────
# Parameter design: 10 (font_pt, line_pt, dpi) combinations, criteria vary
# independently
# ─────────────────────────────────────────────────────────────────────────────
#
# Allowed values:
#   line_pt ∈ {1, 1.5, 2, 2.5, 3}       (PASS if ≥ 2)
#   font_pt ∈ {6, 7, 8, 9, 10}          (PASS if ≥ 8)
#   dpi     ∈ {200, 250, 300, 350, 400} (PASS if ≥ 300)
#
# The 10 combinations mix PASS/FAIL independently per criterion instead of
# moving all three together, so that precision/recall per criterion are
# meaningful and independent.
PARAM_COMBOS = [
    # (font_pt, line_pt, dpi, note)
    (10.0, 3.0, 400, "all PASS (well inside the limits)"),
    (6.0,  1.0, 200, "all FAIL (well outside the limits)"),
    (8.0,  2.0, 300, "all PASS (exactly at the limit, tests sensitivity)"),
    (7.0,  1.5, 250, "all FAIL (just below the limit)"),
    (9.0,  2.5, 350, "all PASS"),
    (7.0,  2.5, 400, "font FAIL / line PASS / DPI PASS"),
    (9.0,  1.5, 200, "font PASS / line FAIL / DPI FAIL"),
    (8.0,  1.0, 350, "font PASS / line FAIL / DPI PASS"),
    (6.0,  3.0, 250, "font FAIL / line PASS / DPI FAIL"),
    (10.0, 2.0, 200, "font PASS / line PASS / DPI FAIL"),
]

PLOT_TYPES = ["pca", "volcano", "heatmap", "boxplot", "bar_error"]


def build_test_configs() -> list[dict]:
    """Build the 50 configurations as PLOT_TYPES × PARAM_COMBOS (5 types × 10)."""
    configs = []
    for plot_type in PLOT_TYPES:
        for idx, (font_pt, line_pt, dpi, note) in enumerate(PARAM_COMBOS, start=1):
            configs.append({
                "type": plot_type,
                "font": font_pt,
                "line": line_pt,
                "dpi": dpi,
                "note": note,
                "name": f"benchmark_{plot_type}_{idx:02d}.png",
            })
    return configs


def main(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)
    test_configs = build_test_configs()
    ground_truth_db = {}

    for config in test_configs:
        fig, ax = plt.subplots(figsize=(TARGET_WIDTH_INCH, TARGET_HEIGHT_INCH))

        plot_type = config["type"]
        font_pt = config["font"]
        line_pt = config["line"]
        dpi = config["dpi"]
        filename = config["name"]
        img_path = output_dir / filename

        if plot_type == "pca":
            draw_pca(ax, font_pt, line_pt)
        elif plot_type == "volcano":
            draw_volcano(ax, font_pt, line_pt)
        elif plot_type == "heatmap":
            draw_heatmap(fig, ax, font_pt, line_pt)
        elif plot_type == "boxplot":
            draw_boxplot(ax, font_pt, line_pt)
        elif plot_type == "bar_error":
            draw_bar_error(ax, font_pt, line_pt)
        else:
            plt.close(fig)
            raise ValueError(f"Unknown chart type: {plot_type}")

        # Make the frame and tick marks use the same line width and font size
        for spine in ax.spines.values():
            spine.set_linewidth(line_pt)

        ax.tick_params(axis="both", labelsize=font_pt, width=line_pt)

        plt.tight_layout()
        plt.savefig(img_path, dpi=dpi, pad_inches=0)
        plt.close(fig)

        ground_truth_db[filename] = {
            "image_path": str(img_path),
            "plot_type": plot_type,
            "figure_width_mm": TARGET_WIDTH_MM,
            "expected_dpi": dpi,
            "expected_min_font_pt": font_pt,
            "expected_line_width_pt": line_pt,
            "note": config["note"],
            "expected_dpi_pass": "PASS" if dpi >= 300 else "FAIL",
            "expected_font_pass": "PASS" if font_pt >= 8.0 else "FAIL",
            "expected_line_pass": "PASS" if line_pt >= 2.0 else "FAIL",
        }

    gt_file_path = output_dir / "benchmark_gt.json"
    with open(gt_file_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth_db, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(test_configs)} benchmark figures")
    print(f"  ({len(PLOT_TYPES)} chart types × {len(PARAM_COMBOS)} physical specifications)")
    print(f"Figures and ground truth saved to: {output_dir.resolve()}")

    # Print the PASS/FAIL distribution, to check that the 10 combinations are balanced
    print("\n=== Ground truth PASS/FAIL distribution ===")
    for criterion_key, label in [
        ("expected_dpi_pass", "DPI"),
        ("expected_font_pass", "Font size"),
        ("expected_line_pass", "Line width"),
    ]:
        pass_count = sum(1 for v in ground_truth_db.values() if v[criterion_key] == "PASS")
        fail_count = len(ground_truth_db) - pass_count
        print(f"[{label}] PASS={pass_count} / FAIL={fail_count}")


if __name__ == "__main__":
    main()
