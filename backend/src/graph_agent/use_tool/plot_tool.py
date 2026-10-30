import datetime
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import matplotlib.cm as cm

# pip install daltonlens
from daltonlens import simulate

# pip install easyocr
import easyocr

# pip install wcag-contrast-ratio
import wcag_contrast_ratio as wcag

# pip install scikit-learn
from sklearn.cluster import KMeans

from langchain.tools import tool


# ─────────────────────────────────────────────────────────────────────────────
# 0. Shared EasyOCR singleton
# ─────────────────────────────────────────────────────────────────────────────

_easyocr_reader: Optional[easyocr.Reader] = None
_ocr_lock = threading.Lock()


def _get_ocr_reader() -> easyocr.Reader:
    """Get the EasyOCR Reader instance as a singleton shared by the whole module."""
    global _easyocr_reader
    if _easyocr_reader is None:
        with _ocr_lock:
            if _easyocr_reader is None:
                _easyocr_reader = easyocr.Reader(["en"], gpu=False)
    return _easyocr_reader


def _ocr_readtext(image) -> List[Any]:
    """Wrap calls in a lock to reduce the risk of concurrent multi-threaded EasyOCR calls."""
    reader = _get_ocr_reader()
    with _ocr_lock:
        return reader.readtext(image)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unit Conversion Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _px_to_pt_via_mm(px: float, px_per_mm: float) -> float:
    """Convert a pixel count to points (pt), based on pixels per millimetre (px/mm). 1 pt ≈ 0.3528 mm"""
    if px_per_mm <= 0:
        return 0.0
    mm = px / px_per_mm
    return mm / 0.3528


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scale & Resolution Analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze_resolution(
    image_path: str,
    is_single_column: bool = True,
    figure_width_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute pixels per millimetre (px/mm) and the effective DPI.

    New figure_width_mm parameter: if the user states the intended print
    width (e.g. a journal requires 90mm), that value takes priority; only
    when it is absent do we fall back to the is_single_column defaults of
    85mm (single column) / 180mm (double column). This way the tool no
    longer assumes every figure is printed at a standard single/double
    column width, and can follow the user's actual submission guidelines.
    """
    if figure_width_mm is not None:
        target_width_mm = float(figure_width_mm)
        single_or_double_column = "custom"
    elif is_single_column:
        target_width_mm = 85.0
        single_or_double_column = "single"
    else:
        target_width_mm = 180.0
        single_or_double_column = "double"

    with Image.open(image_path) as img:
        width, height = img.size
        raw_dpi = img.info.get("dpi", None)

    metadata_dpi = None
    if raw_dpi is not None:
        try:
            metadata_dpi = [float(d) for d in raw_dpi]
        except Exception:
            metadata_dpi = str(raw_dpi)

    width_int = int(width)
    height_int = int(height)

    width_inches = target_width_mm / 25.4
    effective_dpi = float(round(width_int / width_inches, 2)) if width_inches > 0 else 0.0
    px_per_mm = float(width_int / target_width_mm) if target_width_mm > 0 else 0.0
    mm_per_px = float(1.0 / px_per_mm) if px_per_mm > 0 else 0.0

    return {
        "figure_width_mm": float(target_width_mm),
        "single_or_double_column": single_or_double_column,
        "width_px": width_int,
        "height_px": height_int,
        "metadata_dpi": metadata_dpi,
        "effective_dpi": effective_dpi,
        "px_per_mm": px_per_mm,
        "mm_per_px": mm_per_px,
        "warning": (
            "Metadata DPI may be missing or uncalibrated; use effective_dpi for"
            " publication evaluation."
        ),
    }


def dpi_pass_analysis(effective_dpi: float) -> Dict[str, str]:
    """Keep a PASS/FAIL verdict for DPI: one of the few hard requirements stated explicitly by almost every journal."""
    if effective_dpi >= 300:
        return {"dpi_status": "PASS", "dpi_suggestion": "DPI is at least 300; check passed"}
    return {"dpi_status": "FAIL", "dpi_suggestion": "DPI is below 300; please increase the resolution"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Text Size Analysis: measurement only, no PASS/FAIL verdict
# ─────────────────────────────────────────────────────────────────────────────

def estimate_text_size(
    image_path: str, px_per_mm: float
) -> Tuple[List[Dict[str, Any]], List[Any]]:
    """Detect text in the figure with EasyOCR and convert it to font size in points (pt) using the physical scale."""
    results = _ocr_readtext(image_path)

    texts = []
    bboxes = []

    for bbox, text, confidence in results:
        bboxes.append(bbox)

        ys = [point[1] for point in bbox]
        height_px = max(ys) - min(ys)
        size_pt = _px_to_pt_via_mm(height_px, px_per_mm)

        texts.append({
            "text": text,
            "height_px": float(height_px),
            "estimated_pt": round(float(size_pt), 2),
            "confidence": float(confidence),
        })

    return texts, bboxes


def text_size_analysis(
    text_list: List[Dict[str, Any]],
    reference_pt: float = 8.0,
) -> Dict[str, Any]:
    """Measure the text-size distribution and report statistics only, with no PASS/FAIL verdict.

    Rationale: most journals do not state a minimum font size the way
    they do for DPI (or the rule differs per journal), so compliance is
    no longer judged automatically here. We only provide min/avg/the
    ≥reference_pt ratio, and the user checks them against the submission
    guidelines. The reference_pt default of 8.0 is only a common
    reference value; the tool is not making the decision for the user.
    """
    if not text_list:
        return {
            "text_note": "No text detected in the figure",
            "min_pt": None,
            "avg_pt": None,
            "ge_reference_pt_ratio": None,
        }

    pt_sizes = [t.get("estimated_pt", 0) for t in text_list]
    total_count = len(pt_sizes)
    ge_count = sum(1 for pt in pt_sizes if pt >= reference_pt)
    ge_ratio_percent = round(ge_count / total_count * 100, 1)

    return {
        "text_note": (
            f"Detected {total_count} text items: minimum {round(min(pt_sizes), 2)} pt, "
            f"average {round(sum(pt_sizes) / total_count, 2)} pt; "
            f"{ge_ratio_percent}% ({ge_count}/{total_count}) are at least {reference_pt} pt."
            " Please check compliance against the target journal's submission guidelines."
        ),
        "min_pt": round(min(pt_sizes), 2),
        "avg_pt": round(sum(pt_sizes) / total_count, 2),
        "ge_reference_pt_ratio": ge_ratio_percent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Line Width Analysis: measurement only, no PASS/FAIL verdict
# ─────────────────────────────────────────────────────────────────────────────

def _mask_text_regions(
    img: np.ndarray, ocr_bboxes: List[Any], padding: int = 3, fill_value: int = 255
) -> np.ndarray:
    """Mask text regions (paint white / erase) using the OCR bounding boxes."""
    masked_img = img.copy()
    h_img, w_img = masked_img.shape[:2]

    for bbox in ocr_bboxes:
        pts = np.array(bbox, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)
        x_min = max(0, x - padding)
        y_min = max(0, y - padding)
        x_max = min(w_img, x + w + padding)
        y_max = min(h_img, y + h + padding)
        cv2.rectangle(masked_img, (x_min, y_min), (x_max, y_max), fill_value, -1)

    return masked_img


def _remove_filled_blocks(binary: np.ndarray, max_line_width_px: int) -> np.ndarray:
    """Use a morphological opening (White Top-Hat) to filter out large filled
    areas (heatmap cells, bars, etc.) and keep only thin line structures."""
    kernel_size = max_line_width_px * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    tophat = cv2.morphologyEx(binary, cv2.MORPH_TOPHAT, kernel)
    return tophat


def _get_skeleton(binary_img: np.ndarray) -> np.ndarray:
    """Morphology: extract the one-pixel skeleton of a binarized image."""
    skel = np.zeros(binary_img.shape, np.uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    temp_img = binary_img.copy()

    while True:
        eroded = cv2.erode(temp_img, element)
        temp = cv2.dilate(eroded, element)
        temp = cv2.subtract(temp_img, temp)
        skel = cv2.bitwise_or(skel, temp)
        temp_img = eroded.copy()
        if cv2.countNonZero(temp_img) == 0:
            break
    return skel


def estimate_line_width_distance_transform(
    image_path: str,
    px_per_mm: float,
    ocr_bboxes: Optional[List[Any]] = None,
    padding: int = 3,
    max_line_width_px: int = 15,
    save_debug_image: bool = True,
) -> Dict[str, Any]:
    """Estimate line width using a distance transform and skeletonization."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    if ocr_bboxes:
        img = _mask_text_regions(img, ocr_bboxes, padding=padding, fill_value=255)

    input_path = Path(image_path)
    if save_debug_image:
        debug_dir = input_path.parent / "debug_masks"
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / f"{input_path.stem}_masked.png"), img)

    blurred = cv2.GaussianBlur(img, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary = _remove_filled_blocks(binary, max_line_width_px)

    if save_debug_image:
        cv2.imwrite(str(debug_dir / f"{input_path.stem}_binary.png"), binary)

    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    skel = _get_skeleton(binary)
    skel_pixels = skel > 0

    if not np.any(skel_pixels):
        return {"median_width_pt": 0.0, "estimated_true_line_pt": 0.0, "all_widths_pt": []}
    
    all_widths_px = dist[skel_pixels] * 2

    width_px_median = float(np.median(dist[skel_pixels] * 2))
    width_px_p75 = float(np.percentile(dist[skel_pixels] * 2, 75))
    all_widths_pt = [_px_to_pt_via_mm(px, px_per_mm) for px in all_widths_px]

    return {
        "median_width_pt": round(_px_to_pt_via_mm(width_px_median, px_per_mm), 2),
        "estimated_true_line_pt": round(_px_to_pt_via_mm(width_px_p75, px_per_mm), 2),
    }


def line_width_analysis(median_width_pt: float, estimated_true_line_pt: float, reference_pt: float = 2.0) -> Dict[str, Any]:
    """Measure line width and report data only, with no PASS/FAIL verdict.

    Same rationale as text size: most journals set no hard lower limit
    on line width (or the rule differs per journal), so compliance is no
    longer judged automatically. We only report the measured values
    against reference thresholds, and the user checks them against the
    submission guidelines.
    """
    return {
        "line_note": (
            f"Estimated line width (50th percentile): {median_width_pt} pt; "
            f"estimated line width (75th percentile): {estimated_true_line_pt} pt"
            f" (common reference threshold: {reference_pt} pt). Please check compliance against the target journal's submission guidelines."
        ),
        "median_width_pt":median_width_pt,
        "estimated_true_line_pt": estimated_true_line_pt,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Color & Accessibility Module (contrast and colorblind simulation)
# ─────────────────────────────────────────────────────────────────────────────

def _evaluate_text_contrast(img_bgr: np.ndarray) -> Dict[str, Any]:
    """Check the foreground/background contrast of every text region in the image (WCAG 1.4.3)."""
    h_img, w_img = img_bgr.shape[:2]
    results = _ocr_readtext(img_bgr)

    text_results = []
    valid_text_count = 0
    passed_aa = 0

    for bbox, text, confidence in results:
        if confidence < 0.3:
            continue

        pts = np.array(bbox, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)

        padding = 4
        x1, y1 = max(0, x - padding), max(0, y - padding)
        x2, y2 = min(w_img, x + w + padding), min(h_img, y + h + padding)
        crop = img_bgr[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        fg_pixels = crop[thresh > 0]
        bg_pixels = crop[thresh == 0]

        if len(fg_pixels) == 0 or len(bg_pixels) == 0:
            continue

        valid_text_count += 1

        fg_rgb = tuple(np.mean(fg_pixels, axis=0)[::-1] / 255.0)
        bg_rgb = tuple(np.mean(bg_pixels, axis=0)[::-1] / 255.0)

        try:
            ratio = round(float(wcag.rgb(fg_rgb, bg_rgb)), 2)
        except Exception:
            ratio = 1.0

        is_pass = ratio >= 4.5
        if is_pass:
            passed_aa += 1

        text_results.append({
            "text": text,
            "confidence": round(float(confidence), 2),
            "contrast_ratio": ratio,
            "pass_aa": is_pass,
        })

    pass_rate = (passed_aa / valid_text_count) if valid_text_count > 0 else 1.0

    return {
        "total_texts_found": len(results),
        "valid_texts_evaluated": valid_text_count,
        "passed_aa_count": passed_aa,
        "pass_rate": round(pass_rate, 2),
        "compliant": pass_rate >= 0.9,
        "details": text_results,
    }


def _visualize_palette(
    colors_rgb: List[Tuple[int, int, int]], bg_rgb: Tuple[int, int, int], output_path: str
):
    """Draw and save a visualization of the extracted RGB palette."""
    num_colors = len(colors_rgb) + 1
    fig, ax = plt.subplots(figsize=(max(num_colors * 1.5, 3), 2))

    all_colors = [bg_rgb] + colors_rgb
    labels = ["Background"] + [f"Color {i + 1}" for i in range(len(colors_rgb))]

    for i, (col, label) in enumerate(zip(all_colors, labels)):
        color_norm = [c / 255.0 for c in col]
        ax.add_patch(plt.Rectangle((i, 0), 1, 1, color=color_norm, ec="black", lw=1.5))
        text_color = "white" if np.mean(color_norm) < 0.5 else "black"
        ax.text(i + 0.5, 0.5, f"{label}\nRGB\n{col}", ha="center", va="center",
                 color=text_color, fontsize=8, weight="bold")

    ax.set_xlim(0, num_colors)
    ax.set_ylim(0, 1)
    ax.axis("off")
    plt.title("Extracted Palette Preview", fontsize=10, pad=10)
    plt.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _evaluate_non_text_contrast(
    img_bgr: np.ndarray,
    image_path: Optional[str] = None,
    num_colors: int = 5,
    min_pixel_ratio: float = 0.0,
) -> Dict[str, Any]:
    """Extract the main non-background colors of the chart and check their contrast against the background (threshold 3.0:1)."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pixels = img_rgb.reshape(-1, 3) / 255.0

    kmeans = KMeans(n_clusters=num_colors, n_init=5, random_state=42).fit(pixels)
    colors = kmeans.cluster_centers_

    counts = np.bincount(kmeans.labels_)
    total_pixels = len(pixels)
    ratios = counts / total_pixels

    bg_color_idx = int(np.argmax(counts))
    bg_rgb_int = tuple(int(np.clip(c * 255, 0, 255)) for c in colors[bg_color_idx])
    bg_rgb_norm = tuple(c / 255.0 for c in bg_rgb_int)

    palette_results = []
    valid_fg_rgbs = []
    passed_non_text = 0

    for i, color in enumerate(colors):
        if i == bg_color_idx:
            continue
        if ratios[i] < min_pixel_ratio:
            continue

        fg_rgb_int = tuple(int(np.clip(c * 255, 0, 255)) for c in color)
        fg_rgb_norm = tuple(c / 255.0 for c in fg_rgb_int)
        valid_fg_rgbs.append(fg_rgb_int)

        try:
            ratio = round(float(wcag.rgb(fg_rgb_norm, bg_rgb_norm)), 2)
        except Exception:
            ratio = 1.0

        is_pass = ratio >= 3.0
        if is_pass:
            passed_non_text += 1

        palette_results.append({
            "color_rgb": list(fg_rgb_int),
            "pixel_share_percent": round(float(ratios[i]) * 100, 2),
            "contrast_against_bg": ratio,
            "pass_3_to_1": is_pass,
        })

    palette_img_path = None
    if image_path:
        input_path = Path(image_path)
        palette_img_path = str(input_path.parent / "palette" / f"{input_path.stem}_palette_preview.png")
        _visualize_palette(valid_fg_rgbs, bg_rgb_int, palette_img_path)

    non_bg_colors = len(palette_results)
    compliant = (passed_non_text == non_bg_colors) if non_bg_colors > 0 else True

    return {
        "detected_background_rgb": list(bg_rgb_int),
        "all_extracted_colors_rgb": [list(bg_rgb_int)] + [list(c) for c in valid_fg_rgbs],
        "non_bg_colors_count": non_bg_colors,
        "passed_3_to_1_count": passed_non_text,
        "compliant": compliant,
        "palette_image_preview_path": palette_img_path,
        "details": palette_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5b. Pairwise Colorblind Confusability
# ─────────────────────────────────────────────────────────────────────────────
#
# Background: the global grayscale standard-deviation loss rate (see
# _evaluate_colorblind_accessibility) only detects whether overall
# luminance variation is preserved. It easily misses a local but severe
# problem: two colors with opposite meanings (e.g. up-regulated = red,
# down-regulated = green) collapsing into one color under colorblind
# vision. For this reason, authoritative color-science sources such as
# ColorBrewer do not list red-yellow-green diverging colormaps like
# RdYlGn as colorblind safe, even when their global statistics may not
# look like a large loss.

def check_colormap_confusability(
    cmap_name: str, n_samples: int = 10, threshold: float = 10.0
) -> List[Tuple[str, int, int, float]]:
    """Check a matplotlib colormap by name: after colorblind simulation, are
    there sample-point pairs that cannot be told apart? Useful when you know
    which colormap a figure uses and want to test that colormap on its own
    for colorblind safety (e.g. verifying your chosen colormap for a paper).

    Returns: [(deficiency_name, index_i, index_j, simulated_rgb_distance), ...]
    """
    cmap = cm.get_cmap(cmap_name)
    sample_colors = [cmap(i / (n_samples - 1))[:3] for i in range(n_samples)]
    sample_colors_255 = np.array(
        [[int(c * 255) for c in rgb] for rgb in sample_colors], dtype=np.uint8
    )

    simulator = simulate.Simulator_Brettel1997()
    confusable_pairs = []

    for deficiency in [simulate.Deficiency.PROTAN, simulate.Deficiency.DEUTAN, simulate.Deficiency.TRITAN]:
        simulated = simulator.simulate_cvd(
            sample_colors_255.reshape(1, -1, 3), deficiency, severity=1.0
        ).reshape(-1, 3)
        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                dist = float(np.linalg.norm(simulated[i].astype(float) - simulated[j].astype(float)))
                if dist < threshold:
                    confusable_pairs.append((deficiency.name, i, j, round(dist, 2)))

    return confusable_pairs

def _check_palette_pairwise_confusability(
    colors_rgb: List[Tuple[int, int, int]],
    threshold_ab: float = 15,
    threshold_full_lab: float = 20,
) -> Dict[str, Any]:
    """
    Change: add the original (unsimulated) color distance as a baseline, to distinguish:
    - colorblind-specific collapse (original distance is large enough, but the simulated distance falls below the threshold)
      → this is the problem truly attributable to colorblind vision
    - contrast that was already insufficient (even the original distance is below the threshold)
      → this is a general design contrast problem and should not be classed as "not colorblind friendly";
      otherwise the report's attribution misleads the user into changing the "colorblind palette"
      when what needs changing is the overall contrast
    """
    if len(colors_rgb) < 2:
        return {"confusable_pairs": [], "total_pairs_tested": 0,
                "threshold_used_ab": threshold_ab, "compliant": True,
                "note": "Fewer than 2 colors extracted; pairwise comparison is not possible"}

    colors_255 = np.array(colors_rgb, dtype=np.uint8)
    simulator = simulate.Simulator_Brettel1997()
    confusable_pairs = []
    unconfusable_pairs = []
    pre_existing_low_contrast_pairs = []  # 🎯 new: pairs whose contrast was already insufficient
    deficiencies = [("PROTAN", simulate.Deficiency.PROTAN),
                    ("DEUTAN", simulate.Deficiency.DEUTAN),
                    ("TRITAN", simulate.Deficiency.TRITAN)]
    n = len(colors_rgb)
    total_pairs_tested = 0

    # 🎯 First compute the pairwise Lab distances of the original (unsimulated) colors as the baseline
    original_bgr = colors_255[:, ::-1].reshape(-1, 1, 3)
    original_lab = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
    original_ab_dist = {}
    for i in range(n):
        for j in range(i + 1, n):
            l1, a1, b1 = original_lab[i]
            l2, a2, b2 = original_lab[j]
            original_ab_dist[(i, j)] = float(np.linalg.norm([a1 - a2, b1 - b2]))

    for def_name, deficiency in deficiencies:
        simulated_rgb = simulator.simulate_cvd(
            colors_255.reshape(1, -1, 3), deficiency, severity=1.0
        ).reshape(-1, 3)
        simulated_bgr = simulated_rgb[:, ::-1].reshape(-1, 1, 3)
        simulated_lab = cv2.cvtColor(simulated_bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)

        for i in range(n):
            for j in range(i + 1, n):
                total_pairs_tested += 1
                l1, a1, b1 = simulated_lab[i]
                l2, a2, b2 = simulated_lab[j]

                dist_ab = float(np.linalg.norm([a1 - a2, b1 - b2]))
                dist_full = float(np.linalg.norm([l1 - l2, a1 - a2, b1 - b2]))
                orig_dist = original_ab_dist[(i, j)]

                pair_info = {
                    "deficiency": def_name,
                    "color_1_rgb": list(colors_rgb[i]),
                    "color_2_rgb": list(colors_rgb[j]),
                    "original_ab_distance": round(orig_dist, 2),  # 🎯 new
                    "simulated_ab_distance": round(dist_ab, 2),
                    "simulated_full_lab_distance": round(dist_full, 2),
                }

                if orig_dist < threshold_ab:
                    # Already indistinguishable, not caused by colorblindness; put it in the other group
                    pair_info["severity"] = "Insufficient contrast in the original colors (not a colorblind-specific problem)"
                    pre_existing_low_contrast_pairs.append(pair_info)
                elif dist_ab < threshold_ab:
                    # Distinguishable originally but collapsed after simulation: the true colorblind-specific problem
                    severity = "Severe (lightness also fails to separate the pair)" if dist_full < threshold_full_lab else "Moderate (lightness may separate the pair, but the risk is still high)"
                    pair_info["severity"] = severity
                    confusable_pairs.append(pair_info)
                else:
                    pair_info["severity"] = "Acceptable separation"
                    unconfusable_pairs.append(pair_info)

    return {
        "confusable_pairs": confusable_pairs,
        "pre_existing_low_contrast_pairs": pre_existing_low_contrast_pairs,  # 🎯 new
        "unconfusable_pairs": unconfusable_pairs,
        "total_pairs_tested": total_pairs_tested,
        "threshold_used_ab": threshold_ab,
        "compliant": len(confusable_pairs) == 0,
        "note": (
            f"{len(pre_existing_low_contrast_pairs)} color pairs already have insufficient contrast in the original colors (without colorblind simulation). "
            f"Tested {total_pairs_tested} colorblind-type/color-pair combinations; {len(confusable_pairs)} triggered the confusion threshold. "
            "Hue collapse is the main criterion (data points in scientific figures are usually small, so readers are not assumed to reliably distinguish subtle lightness differences). "
            "Each pair is also flagged for whether lightness also fails to separate it (severity), so you can judge the risk level instead of relying on a single binary verdict. "
            f"Severe: the full CIELAB distance (including lightness) is < {threshold_full_lab}. Moderate: the chroma (a*b*) distance is < {threshold_ab}, but the full CIELAB distance (including lightness) is >= {threshold_full_lab}."
        ),
    }

# result = _check_palette_pairwise_confusability([[0, 255, 0],[255, 0, 0]])
# print(result)
# {'confusable_pairs': [{'deficiency': 'DEUTAN', 'color_1_rgb': [0, 255, 0], 'color_2_rgb': [255, 0, 0], 'simulated_ab_distance': 14.14, 'simulated_full_lab_distance': 68.48, 'severity': '<"moderate (lightness may help, but risk is still high)">'}], 'total_pairs_tested': 3, 'threshold_used_ab': 18.0, 'compliant': False, 'note': '<note: 3 pairwise colorblind chroma (a*b*) comparisons done (threshold < 18.0); hue collapse is the main criterion, with a severity flag for whether lightness also fails to separate the pair>'}

def _evaluate_colorblind_accessibility(
    img_bgr: np.ndarray,
    extracted_colors_rgb: Optional[List[Tuple[int, int, int]]] = None,
    image_path: Optional[str] = None,
    save_simulated_images: bool = True,
    confusability_threshold: float = 15,  
) -> Dict[str, Any]:
    """Simulate colorblind vision with Daltonlens and combine the global
    grayscale standard-deviation loss rate with pairwise color confusability
    to assess colorblind friendliness comprehensively.

    Rationale: compliant now requires both conditions to pass:
    (1) global information loss rate < 15% (the original overall luminance-variation check)
    (2) no pair of the colors actually used in the image becomes indistinguishable under colorblind vision
    The two complement each other, so a local but severe red-green confusion is not missed by looking only at global statistics.
    """
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    gray_orig = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    orig_std = float(np.std(gray_orig))

    simulator = simulate.Simulator_Brettel1997()
    output_files = []
    colorblind_dir = None
    input_path = None
    formatted_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    if image_path and save_simulated_images:
        input_path = Path(image_path)
        output_dir = input_path.parent.parent
        colorblind_dir = output_dir / "colorblind"
        colorblind_dir.mkdir(parents=True, exist_ok=True)

        gray_output_path = colorblind_dir / f"{input_path.stem}_grayscale_{formatted_time}.png"
        Image.fromarray(gray_orig).save(gray_output_path)
        output_files.append(str(gray_output_path))

    deficiencies = [simulate.Deficiency.PROTAN, simulate.Deficiency.DEUTAN, simulate.Deficiency.TRITAN]
    loss_ratios = {}

    for deficiency in deficiencies:
        cvd_im_rgb = simulator.simulate_cvd(img_rgb, deficiency, severity=1.0)
        cvd_gray = cv2.cvtColor(cvd_im_rgb, cv2.COLOR_RGB2GRAY)
        cvd_std = float(np.std(cvd_gray))

        loss = (orig_std - cvd_std) / orig_std if orig_std > 0 else 0.0
        loss_ratios[deficiency.name] = round(float(loss), 3)

        if image_path and save_simulated_images and colorblind_dir and input_path:
            output_filename = f"{input_path.stem}_{deficiency.name}_{formatted_time}.png"
            output_path = colorblind_dir / output_filename
            Image.fromarray(cvd_im_rgb).save(output_path)
            output_files.append(str(output_path))

    max_loss_ratio = max(loss_ratios.values()) if loss_ratios else 0.0
    global_compliant = max_loss_ratio < 0.15

    if extracted_colors_rgb and len(extracted_colors_rgb) >= 2:
        pairwise_result = _check_palette_pairwise_confusability(
            extracted_colors_rgb, threshold_ab=confusability_threshold
        )
    else:
        pairwise_result = {
            "confusable_pairs": [],
            "pre_existing_low_contrast_pairs":[],
            "unconfusable_pairs":[],
            "total_pairs_tested": 0,
            "threshold_used": confusability_threshold,
            "compliant": True,
            "note": "Not enough extracted palette colors (fewer than 2); pairwise comparison skipped"
        }

    overall_compliant = global_compliant and pairwise_result["compliant"]

    return {
        "max_information_loss_ratio": max_loss_ratio,
        "loss_ratios_by_type": loss_ratios,
        "global_std_based_compliant": global_compliant,
        "pairwise_confusability": pairwise_result,
        "compliant": overall_compliant,
        "saved_simulated_files": output_files,
        "warning": "Use additional visual cues (such as marker shapes, dashed lines, or text labels) to ensure compliance with WCAG 1.4.1.",
    }


def evaluate_png_wcag21(image_path: str) -> Dict[str, Any]:
    """Run a full WCAG 2.1 assessment on a single image."""
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Cannot read image: {image_path}")

    text_eval = _evaluate_text_contrast(img_bgr)
    non_text_eval = _evaluate_non_text_contrast(img_bgr, image_path)

    # Pass the actual colors extracted by K-means (background + foreground) to the colorblind confusability check
    extracted_colors = [tuple(c) for c in non_text_eval.get("all_extracted_colors_rgb", [])]
    colorblind_eval = _evaluate_colorblind_accessibility(
        img_bgr, extracted_colors_rgb=extracted_colors, image_path=image_path
    )

    overall_compliant = (
        text_eval["compliant"] and non_text_eval["compliant"] and colorblind_eval["compliant"]
    )

    return {
        "overall_wcag21_aa_compliant": overall_compliant,
        "criteria_summary": {
            "1.4.3_text_contrast_min_4.5_to_1": "PASS" if text_eval["compliant"] else "FAIL",
            "1.4.11_non_text_contrast_min_3.0_to_1": "PASS" if non_text_eval["compliant"] else "FAIL",
            "1.4.1_use_of_color_colorblind_safe": "PASS" if colorblind_eval["compliant"] else "FAIL",
        },
        "detailed_results": {
            "text_contrast": text_eval,
            "non_text_contrast": non_text_eval,
            "colorblind_accessibility": colorblind_eval,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. LangChain Main Agent Tool
# ─────────────────────────────────────────────────────────────────────────────

def _to_native(obj):
    """Recursively convert numpy types to native Python types, so LangGraph's
    msgpack checkpoint serialization does not fail."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return _to_native(obj.tolist())
    return obj


@tool
def figure_compliance_checker(
    path: str,
    is_single_column: bool = True,
    figure_width_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Analyze the objective physical properties of an academic figure and its WCAG accessibility compliance.

    - DPI: gives an explicit PASS/FAIL verdict (≥300dpi is a common hard requirement across the industry).
    - Text size, line width: measurement data only, no PASS/FAIL verdict (most journals have no
      uniform hard requirement; check against your submission guidelines).
    - Colorblind friendliness: combines the global grayscale standard-deviation loss rate with pairwise color confusability.

    Args:
        path: path to the image file.
        is_single_column: when figure_width_mm is not given, chooses single-column (85mm)
            or double-column (180mm) width as the assumed print width.
        figure_width_mm: the user can give the intended print width (mm) directly; if given,
            it takes priority over the is_single_column default.
    """
    resolution = analyze_resolution(path, is_single_column, figure_width_mm)
    dpi_pass = dpi_pass_analysis(resolution["effective_dpi"])

    text_analysis, ocr_bboxes = estimate_text_size(path, resolution["px_per_mm"])
    text_report = text_size_analysis(text_analysis)

    line_analysis = estimate_line_width_distance_transform(
        path, resolution["px_per_mm"], ocr_bboxes=ocr_bboxes, padding=3
    )
    line_report = line_width_analysis(line_analysis["median_width_pt"],line_analysis["estimated_true_line_pt"])

    wcag_report = evaluate_png_wcag21(path)

    status = {
        "dpi_pass": dpi_pass["dpi_status"],
        "dpi_suggestion": dpi_pass["dpi_suggestion"],
        "text_note": text_report["text_note"],
        "line_note": line_report["line_note"],
    }

    result = {
        "file_path": path,
        "scale_resolution": resolution,
        "text_analysis": text_analysis,
        "text_report": text_report,
        "line_analysis": line_analysis,
        "line_report": line_report,
        "pass_status": status,
        "wcag_report": wcag_report,
    }
    return _to_native(result)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Markdown report generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_figure_report(data: Dict[str, Any]) -> str:
    """Convert the dict returned by figure_compliance_checker into a Markdown report."""
    if "error" in data:
        return f"# ⚠️ Physical check failed\n\nError: {data['error']}\n"

    scale = data.get("scale_resolution", {})
    text_list = data.get("text_analysis", [])
    text_report = data.get("text_report", {})
    line_report = data.get("line_report", {})
    pass_status = data.get("pass_status", {})
    wcag = data.get("wcag_report", {})

    criteria_summary = wcag.get("criteria_summary", {})
    text_wcag_details = wcag.get("detailed_results", {}).get("text_contrast", {})
    non_text_wcag_details = wcag.get("detailed_results", {}).get("non_text_contrast", {})
    cb_details = wcag.get("detailed_results", {}).get("colorblind_accessibility", {})

    def fmt_status(status_str) -> str:
        s = str(status_str).upper()
        if s in ["PASS", "TRUE", "COMPLIANT"]:
            return "🟢 **PASS**"
        elif s in ["FAIL", "FALSE", "NON-COMPLIANT"]:
            return "🔴 **FAIL**"
        return "—"

    md = []
    md.append("# 📊 Objective Physical and WCAG Compliance Report for Scientific Figures\n")
    md.append("> *Note: most values are estimates from image-processing algorithms and may differ slightly from the true boundaries.*\n")
    md.append(
        "> *Text size and line width are reported as measurements only, with no PASS/FAIL verdict"
        " (most journals have no uniform rule; please check the submission guidelines). DPI is a near-universal hard requirement,"
        " so it still receives an explicit verdict.*\n"
    )

    md.append("## 1. Physical Properties Overview (Executive Summary)\n")
    md.append("| Check | Measurement / Result | Reference Standard | Status | Notes |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")

    w_px = scale.get("width_px", "N/A")
    h_px = scale.get("height_px", "N/A")
    w_mm = scale.get("figure_width_mm", 85.0)
    col_type = scale.get("single_or_double_column", "single").capitalize()
    md.append(
        f"| **Figure Size (Scale)** | {w_px} × {h_px} px (print width {w_mm} mm) |"
        f" {col_type} ({w_mm} mm) | — | — |"
    )

    eff_dpi = round(float(scale.get("effective_dpi", 0)), 2)
    md.append(
        f"| **Effective Resolution (Effective DPI)** | **{eff_dpi} DPI** | ≥ 300 DPI (near-universal hard requirement) |"
        f" {fmt_status(pass_status.get('dpi_pass'))} | inch-to-mm conversion introduces some error |"
    )

    min_pt = text_report.get("min_pt", "N/A")
    avg_pt = text_report.get("avg_pt", "N/A")
    ge_ratio = text_report.get("ge_reference_pt_ratio", "N/A")
    md.append(
        f"| **Text Size** | min **{min_pt} pt** / avg **{avg_pt} pt** /"
        f" ≥8pt ratio **{ge_ratio}%** | Varies by journal | *For reference only; use your own judgment* |"
        " Most journals set no uniform minimum font size |"
    )
    med_line = line_report.get("median_width_pt", "N/A")
    est_line = line_report.get("estimated_true_line_pt", "N/A")
    md.append(
        f"| **Line Width** | estimated **{med_line} pt** (50th percentile), **{est_line} pt** (75th percentile) | Varies by journal |"
        " *For reference only; use your own judgment* | Most journals set no uniform minimum line width |"
    )

    t_pass = text_wcag_details.get("passed_aa_count", 0)
    t_total = text_wcag_details.get("valid_texts_evaluated", 0)
    t_rate = round(text_wcag_details.get("pass_rate", 0) * 100, 1)
    md.append(
        f"| **Text WCAG Contrast (1.4.3)** | pass rate **{t_rate}%** ({t_pass}/{t_total} items) |"
        f" ≥ 4.5:1 | {fmt_status(criteria_summary.get('1.4.3_text_contrast_min_4.5_to_1'))} |"
        " Contrast between text and background colors |"
    )

    nt_pass = non_text_wcag_details.get("passed_3_to_1_count", 0)
    nt_total = non_text_wcag_details.get("non_bg_colors_count", 0)
    md.append(
        f"| **Graphics WCAG Contrast (1.4.11)** | pass rate **{nt_pass}/{nt_total}** palette colors |"
        f" ≥ 3.0:1 | {fmt_status(criteria_summary.get('1.4.11_non_text_contrast_min_3.0_to_1'))} |"
        " Contrast between non-text elements and background colors |"
    )

    max_loss = round(float(cb_details.get("max_information_loss_ratio", 0)) * 100, 1)
    global_ok = cb_details.get("global_std_based_compliant", True)
    pairwise = cb_details.get("pairwise_confusability", {})
    n_confusable = len(pairwise.get("confusable_pairs", []))
    n_unconfusable = len(pairwise.get("unconfusable_pairs", []))
    n_preconfusable = len(pairwise.get("pre_existing_low_contrast_pairs",[]))
    md.append(
        f"| **Colorblind Friendliness (1.4.1)** | global information loss **{max_loss}%**"
        f" ({'PASS' if global_ok else 'FAIL'}) / pairwise confusable pairs **{n_confusable}** |"
        f" Loss rate < 15% and no confusable pairs | {fmt_status(criteria_summary.get('1.4.1_use_of_color_colorblind_safe'))} |"
        " Pairwise confusability catches red-green confusion that global statistics miss |\n"
    )
    md.append(f"> *{cb_details.get('warning', '')}*\n")

    # ── Text recognition details ──────────────────────────────────────
    md.append("## 2. Text Recognition and Contrast Details (Top 10)\n")
    md.append("| Recognized Text | Height (px) | Estimated Size (pt) | Contrast | WCAG Contrast (≥4.5:1) |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")

    wcag_details_map = {d.get("text"): d for d in text_wcag_details.get("details", [])}

    for t in text_list:
        txt = t.get("text", "")
        h_px_val = round(float(t.get("height_px", 0)), 1)
        est_pt = round(float(t.get("estimated_pt", 0)), 2)
        wcag_info = wcag_details_map.get(txt, {})
        ratio = round(float(wcag_info.get("contrast_ratio", 0)), 2)
        contrast_pass = wcag_info.get("pass_aa", False)

        md.append(
            f"| `{txt}` | {h_px_val} px | **{est_pt} pt** | {ratio} : 1 | {fmt_status(contrast_pass)} |"
        )
    # ── Palette and colorblind-friendliness analysis ──────────────────
    md.append("## 3. Palette Contrast Analysis\n")
    bg_rgb = non_text_wcag_details.get("detected_background_rgb", [255, 255, 255])
    md.append(f"**Detected background color**: `RGB{tuple(bg_rgb)}` | **WCAG threshold for non-text objects**: `3.0:1`\n")
    md.append("| Swatch | Color RGB | Share | Contrast (Ratio) | WCAG 3.0:1 Threshold |")
    md.append("| :---: | :--- | :--- | :--- | :--- |")

    for item in non_text_wcag_details.get("details", []):
        c_rgb = tuple(item.get("color_rgb", [0, 0, 0]))
        ratio = round(float(item.get("contrast_against_bg", 0)), 2)
        share = item.get("pixel_share_percent", 0)
        color_box = (
            f'<span style="display:inline-block; width:24px; height:14px;'
            f' background-color:rgb{c_rgb}; border:1px solid #aaa;'
            ' border-radius:2px;"></span>'
        )
        md.append(f"| {color_box} | `RGB{c_rgb}` | {share}% | **{ratio} : 1** | {fmt_status(item.get('pass_3_to_1'))} |")
    md.append("")

    loss_map = cb_details.get("loss_ratios_by_type", {})
    md.append("**Global information loss rate by simulated colorblindness type**:")
    for deficiency, loss in loss_map.items():
        md.append(f"- **{deficiency}**: `{round(float(loss) * 100, 1)}%`")
    md.append("")

    # ── Pairwise colorblind confusability details ─────────────────────
    md.append("## 4. Pairwise Colorblind Confusability Check (Pairwise Confusability)\n")
    total_tested = pairwise.get("total_pairs_tested", 0)
    thresh = pairwise.get("threshold_used",15)
    if n_preconfusable > 0:
        md.append(f"⚠️ **Result**: {(n_preconfusable)} color pairs already have insufficient contrast in the original colors, without colorblind simulation (threshold distance < {thresh}):\n")
        md.append("| Colorblind Type | Color 1 (RGB) | Color 2 (RGB) | Distance Before Simulation | Full CIELAB Distance (incl. Lightness) | Note |")
        md.append("| :--- | :--- | :--- | :--- |:--- |:--- |")
        for pre_pair in pairwise["pre_existing_low_contrast_pairs"]:
            md.append(
                f"| - | `RGB{tuple(pre_pair['color_1_rgb'])}` |"
                f" `RGB{tuple(pre_pair['color_2_rgb'])}` | **{pre_pair['original_ab_distance']}** |**{pre_pair['simulated_full_lab_distance']}** |**{pre_pair['severity']}** |"
            )
        md.append("")

    if n_confusable > 0:
        md.append(f"⚠️ **Result**: compared **{total_tested}** color combinations and found **{n_confusable}** colorblind-confusable pairs (threshold distance < {thresh}):\n")
        md.append("| Colorblind Type | Color 1 (RGB) | Color 2 (RGB) | Distance After Simulation | Full CIELAB Distance (incl. Lightness) | Note |")
        md.append("| :--- | :--- | :--- | :--- |:--- |:--- |")
        for pair in pairwise["confusable_pairs"]:
            md.append(
                f"| {pair['deficiency']} | `RGB{tuple(pair['color_1_rgb'])}` |"
                f" `RGB{tuple(pair['color_2_rgb'])}` | **{pair['simulated_ab_distance']}** |**{pair['simulated_full_lab_distance']}** |**{pair['severity']}** |"
            )
        md.append("")
        md.append(f"Remaining pairs that passed the threshold: **{n_unconfusable}** (threshold distance < {thresh}):\n")
        md.append("| Colorblind Type | Color 1 (RGB) | Color 2 (RGB) | Distance After Simulation | Full CIELAB Distance (incl. Lightness) | Note |")
        md.append("| :--- | :--- | :--- | :--- |:--- |:--- |")
        
        for unpair in pairwise["unconfusable_pairs"]:
            md.append(
                f"| {unpair['deficiency']} | `RGB{tuple(unpair['color_1_rgb'])}` |"
                f" `RGB{tuple(unpair['color_2_rgb'])}` | **{unpair['simulated_ab_distance']}** |**{unpair['simulated_full_lab_distance']}** |**{unpair['severity']}** |"
            )
        md.append("")
        md.append(f"> *{pairwise.get('note', '')}*\n")
    else:
        md.append(f"🟢 **Result**: completed **{total_tested}** pairwise color comparisons (threshold distance < {thresh}); **check passed**, no confusable pairs found.\n")
        md.append("| Colorblind Type | Color 1 (RGB) | Color 2 (RGB) | Distance After Simulation | Full CIELAB Distance (incl. Lightness) | Note |")
        md.append("| :--- | :--- | :--- | :--- |:--- |:--- |")
        
        for unpair in pairwise["unconfusable_pairs"]:
            md.append(
                f"| {unpair['deficiency']} | `RGB{tuple(unpair['color_1_rgb'])}` |"
                f" `RGB{tuple(unpair['color_2_rgb'])}` | **{unpair['simulated_ab_distance']}** |**{unpair['simulated_full_lab_distance']}** |**{unpair['severity']}** |"
            )
        md.append("")
        md.append(f"> *{pairwise.get('note', '')}*\n")

    return "\n".join(md)