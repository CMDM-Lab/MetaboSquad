#                     ┌─────────────────────────────────────────┐
#                     │               Input image               │
#                     └────────────────────┬────────────────────┘
#                                          │
#                  ┌───────────────────────┴───────────────────────┐
#                  ▼                                               ▼
#     [Deterministic physical tools (Python)]    [Vision LLM semantic review]
#     1. Pillow (DPI & pixel resolution)         1. Chart type & scientific meaning
#     2. PaddleOCR (text pixel height -> pt)     2. Axis labels & unit sanity
#     3. OpenCV (line pixel width -> pt)         3. Layout & overall aesthetics
#     4. DaltonLens (colour-blind simulation)
#                  │                                               │
#                  └───────────────────────┬───────────────────────┘
#                                          │
#                                          ▼
#                    [Synthesized review report (Synthesize Node)]
#                    - Combine quantitative results with the LLM's semantic suggestions
#                    - Output a review report (.md) that meets journal standards
import os

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
import base64
from pathlib import Path


from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from src.graph_agent.use_tool.plot_tool import figure_compliance_checker, generate_figure_report
from src.graph_agent.state import PlotReviewState
import contextvars
from dotenv import load_dotenv
load_dotenv()
llm_vision = ChatOpenAI(model="gpt-4.1-mini", temperature=0)   # supports vision


PLOT_REVIEW_SYSTEM = """
You are a senior scientific chart review expert for top-tier journals such as Nature and Cell.
Your core task is to conduct an expert review of the visual semantics and layout of scientific figures, strictly evaluating them against the following three criteria.
### Visual & Semantic Review Focus:
1. Axis Titles & Units (Axis Integrity):
   - Both X and Y axes must have explicit title text with sufficient context (variable name, unit, or percentage) — not blank, not default text.
   - Axis ticks and numbers must be legible without overlapping, crowding, or truncation.
2. Colorblind-Safe Palette (Accessibility):
   - Category-Differentiation Check: If Red and Green are the SOLE means of distinguishing categories (e.g., PCA groups, up/down-regulated genes, discrete bar/box colors), flag as a concern.
     * Exception: Resolved if accompanied by non-color redundant encoding (distinct shapes, line styles, hatching, or text labels). State these markers explicitly.
   - Large-Area Usage Check: Independently, check if Red and Green jointly dominate a large, continuous portion of the figure (e.g., heatmap fills, shaded regions, a red-to-green gradient scale). Estimate the approximate area proportion.
     * Exception: Resolved if the area includes redundant encoding (colorbar with directional labels, contour lines, hatching, or numeric annotations). State these explicitly.
   - Verdict: "Non-compliant" if EITHER check has an unresolved concern. "Compliant" only if both are resolved.
3. Legend Legibility, Placement & Overlap (Legend Occlusion Scan):
   - Presence: A legend must be present when the chart shows multiple data series. Missing when required → "Non-compliant". Not needed (single-series, colorbar-based heatmap) → "Not Applicable".
   - Mandatory Collision Check: (1) Locate the legend's bounding box. (2) Scan its surrounding area. (3) Check for ANY overlap with data markers, scatter points, bars, trend lines, error bars/whiskers/CI ribbons, axis labels, or annotations.
   - Verdict — fails if ANY of the following holds:
     * Center Placement: legend sits at/near the plot's visual center — always "Non-compliant", regardless of actual overlap.
     * Data Collision: any data element touches or passes behind the legend frame (even if semi-transparent).
     * Safe Placement (required for "Compliant"): legend sits strictly in dead white space inside the plot, or outside the plot canvas, and away from the visual center.
---
### Strict Output Format Instructions:
Output ONLY the following format — no preamble, no closing remarks. Max 3 items under Modifications & Recommendations.
Image Type: <Chart Type>
Scientific Significance: <1-2 sentences>
Visual & Semantic Review:
- Axis Titles & Units: <Compliant / Non-compliant> — <brief reason>
- Colorblind-Safe Palette: <Compliant / Non-compliant> — <state category-differentiation result and large-area result separately; note any redundant markers/encodings; if Non-compliant, specify which check triggered it>
- Legend Legibility: <Compliant / Non-compliant / Not Applicable> — <legend position, whether near center, whether any element is obscured>
Visual & Layout Deficiencies:
- <Bullet list; "None" if no issues>
Modifications & Recommendations (Max 3 items):
1. <Action 1>
2. <Action 2>
3. <Action 3>
Please respond in Traditional Chinese (繁體中文).
"""

def _load_image_as_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@retry(
    stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
)
def _process_single_file(fpath: str, query: str) -> dict[str, any]:
    file_name = Path(fpath).name
    
    try:
        compliance_res = figure_compliance_checker.invoke({"path": fpath})
    except Exception as e:
        compliance_res = {"error": f"物理檢測失敗: {str(e)}"}

    suffix = Path(fpath).suffix.lower()
    warning = (
        "JPG 的有損壓縮可能引入邊緣模糊影響偵測精確度" if suffix != ".png" else ""
    )

    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
    }.get(suffix, "image/png")

    b64 = _load_image_as_base64(fpath)
    image_content = {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    }

    user_content = [image_content, {"type": "text", "text": query}]
    resp = llm_vision.invoke([
        SystemMessage(content=PLOT_REVIEW_SYSTEM),
        HumanMessage(content=user_content),
    ])

    return {
        "file_path": fpath,
        "file_name": file_name,
        "feedback": resp.content,
        "compliance_result": compliance_res,
        "warning": warning,
    }


# ── 1. Parallel Plot Review Node ──────────────────────────────────────────────
def plot_review_node(state: PlotReviewState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Plot review is in progress..."})

    files = state.get("files", [])
    query = state.get("original_query", "請審查此圖表")

    if not files:
        return {
            "messages": [
                AIMessage(
                    content="Image not found. Please upload images or provide file paths."
                )
            ],
            "review_result": [],
            "figure_compliance_check": [],
        }

    review_results_map = {}
    compliance_results_map = {}

    
    with ThreadPoolExecutor(max_workers=min(10, len(files))) as executor:
        futures = {
            executor.submit(
                contextvars.copy_context().run, _process_single_file, fpath, query
            ): idx
            for idx, fpath in enumerate(files)
        }
        
        for future in as_completed(futures):
            idx = futures[future]
            fpath = files[idx]
            file_name = Path(fpath).name

            try:
                res = future.result()
                review_results_map[idx] = res
                compliance_results_map[idx] = res["compliance_result"]
            except Exception as e:
                review_results_map[idx] = {
                    "file_path": fpath,
                    "file_name": file_name,
                    "feedback": f"審查失敗，錯誤原因：{str(e)}",
                }
                compliance_results_map[idx] = {
                    "file_path": fpath,
                    "file_name": file_name,
                    "error": f"檢測失敗：{str(e)}",
                }

    review_results = [
        review_results_map[idx] for idx in sorted(review_results_map.keys())
    ]
    figure_compliance_checks = [
        compliance_results_map[idx]
        for idx in sorted(compliance_results_map.keys())
    ]

    summary_msg = f"已完成 {len(review_results)} 張圖片的物理合規性檢測與 Vision LLM 審查。"

    return {
        "messages": [AIMessage(content=summary_msg)],
        "review_result": review_results,
        "figure_compliance_check": figure_compliance_checks,
    }


# ── 2. Output Node that writes reports in parallel/batches ─────────────────────
def write_plot_output_node(
    state: PlotReviewState, config: RunnableConfig
) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Report writing now in progress..."})

    date = state.get("date", datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
    folder_path = f"uploads/output/plot_review/{date}"
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    review_results = state.get("review_result", [])
    compliance_checks = state.get("figure_compliance_check", [])
    output_paths = []

    for idx, item in enumerate(review_results):
        file_name = item.get("file_name", f"image_{idx+1}")
        stem_name = Path(file_name).stem
        feedback = item.get("feedback", "無建議內容")

        comp_data = (
            compliance_checks[idx] if idx < len(compliance_checks) else {}
        )
        formatted_tool_report = generate_figure_report(comp_data)

        file_path = f"{folder_path}/result_{stem_name}_{date}.md"

        content = f"""# 圖片審查報告 - {file_name}

**產生時間**：{date}
**圖片檔名**：{file_name}
**原始研究問題**：{state.get('original_query', 'N/A')}

---

## I. LLM 視覺語意與排版審查建議
{feedback}

---

## II. OpenCV / OCR 物理與 WCAG 客觀檢測報告
{formatted_tool_report}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        output_paths.append(file_path)

    if writer:
        writer(
            {
                "status": "Report writing complete.",
                "output_file_path": folder_path,
            }
        )

    path_summary = "\n".join([f"* `{p}`" for p in output_paths])

    return {
        "messages": [
            AIMessage(
                content=(
                    "所有查詢報告已成功儲存至"
                    f" `{folder_path}` 資料夾：\n{path_summary}"
                )
            )
        ],
        "output_path": folder_path,
    }


def build_plot_review_graph():
    builder = StateGraph(PlotReviewState)
    builder.add_node("plot_review", plot_review_node)
    builder.add_node("write_plot_output", write_plot_output_node)
    builder.add_edge(START, "plot_review")
    builder.add_edge("plot_review", "write_plot_output")
    builder.add_edge("write_plot_output", END)
    return builder.compile()


plot_review_graph = build_plot_review_graph()
