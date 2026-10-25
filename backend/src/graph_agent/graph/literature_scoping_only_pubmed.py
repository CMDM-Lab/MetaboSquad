from __future__ import annotations
from datetime import datetime

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential
import contextvars
from src.graph_agent.tools import (query_expansion,
    search_pubmed, search_abstract, write_file, 
    title_filter_tool, abstract_filter_tool, 
    abstract_extract, summary_tool
)

# ── Models and state ─────────────────────────────────────────────────────────────────────
from src.graph_agent.state import LitPubState

# ── LLM ──────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── Nodes ─────────────────────────────────────────────────────────────────────

def expand_query_node(state: LitPubState, config: RunnableConfig) -> dict:
    query = state["original_query"]
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "expand_query"})
    
    # Run structured generation
    result = query_expansion(query)


    return {
        "pubmed_query": result.pubmed_query,      
    }


def search_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Now searching in progress."})
    query  = state["pubmed_query"]
    results: list[dict] = search_pubmed.invoke({"query":query})
    

    return {"search_results": results}


def title_filter_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Merge complete, now title filtering in progress."})
    papers = state.get("search_results", [])
    chunk_size = 80
    
    chunks = [papers[i:i+chunk_size] 
              for i in range(0, len(papers), chunk_size)]
    
    ranked_map = {}
    
    @retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=1, min=2, max=10))
    def _invoke_with_retry(chunk, question):
        return title_filter_tool(chunk, question)

    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(contextvars.copy_context().run, _invoke_with_retry, chunk, state["original_query"]): idx
            for idx, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            ranked_map[idx] = future.result()
    
    # Merge in the original order
    ranked = []
    for idx in sorted(ranked_map.keys()):
        ranked.extend(ranked_map[idx])
    
    return {"title_filter": ranked}

def abstract_filter_node(state: LitPubState, config: RunnableConfig) -> dict:
    """Fetch abstracts, by source, for the papers whose titles passed screening, and assess their relevance"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Title filtering complete, now abstract filtering in progress."})

    title_filter_results = state.get("title_filter", [])
    relevant_papers = [p for p in title_filter_results if p.get("title_decision") == "relevant"]
    
    if not relevant_papers:
        return {"abstract_filter": []}
        
    print(f"abstract_filter_node: {len(relevant_papers)} 篇進入摘要獲取階段")
    
    # Build the per-source lists
    pubmed_ids = []

    abstract_map = {}
    for paper in relevant_papers:
        pmid = paper.get("pmid")
        pubmed_ids.append(pmid)

    if pubmed_ids:
        print(f"[Abstract Node] 正在向 PubMed 請求 {len(pubmed_ids)} 篇摘要...")
        pubmed_data = search_abstract.invoke({"all_ids": pubmed_ids})
        for item in pubmed_data:
            if item.get("pmid"):
                abstract_map[str(item["pmid"])] = item["abstract"]

    # Put the matching abstracts back into the original paper structures
    for paper in relevant_papers:
        pmid = str(paper.get("pmid", ""))
        
        # Look up the abstract in the mapping: try pmid first, then openalex_id
        if pmid in abstract_map:
            paper["abstract"] = abstract_map[pmid]
        else:
            paper["abstract"] = "N/A"
        
    # Classify abstracts in parallel
    chunk_size = 15
    chunks = [relevant_papers[i:i+chunk_size]
              for i in range(0, len(relevant_papers), chunk_size)]
    
    ranked_map = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                contextvars.copy_context().run,
                abstract_filter_tool,
                chunk, state["original_query"]
            ): idx
            for idx, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            ranked_map[idx] = future.result()

    ranked = []
    for idx in sorted(ranked_map.keys()):
        ranked.extend(ranked_map[idx])
        
    return {"abstract_filter": ranked}


def abstract_extract_node(state: LitPubState, config: RunnableConfig) -> dict:
    """Data extraction (abstract-only path)"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Title filtering complete, now abstract filtering in progress."})
    abstract_filter = state.get("abstract_filter", [])
    relevant_papers = [p for p in abstract_filter if p.get("abstract_decision") == "relevant"]

    print(f"abstract_extract_node: {len(relevant_papers)} 篇進入純摘要萃取")

    chunk_size = 1
    chunks = [relevant_papers[i:i+chunk_size] for i in range(0, len(relevant_papers), chunk_size)]

    ranked_map = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(contextvars.copy_context().run, abstract_extract, chunk, state["original_query"]): idx
            for idx, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            ranked_map[idx] = future.result()

    extracted = []
    for idx in sorted(ranked_map.keys()):
        extracted.extend(ranked_map[idx])

    for p in extracted:
        p["text_source"] = "abstract_structured"

    return {
        "abstract_extract": extracted, 
    }
    

def summary_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Literature search completed, summary now in progress."})
    all_extracted_papers = state.get("abstract_extract", [])
    positive_papers, negative_papers, neutral_papers = [], [], []


    # Keep the original classification logic for now and group all extracted papers
    for i in all_extracted_papers:
        direction = str(i.get("direction", "")).lower().strip()
        
        if "positive" in direction:
            positive_papers.append(i)
        elif "negative" in direction:
            negative_papers.append(i)
        elif "neutral" in direction:
            neutral_papers.append(i)
        else:
            print(f"無法識別的 direction 格式: {direction}")
            neutral_papers.append(i)

    # Define the list of tasks to run in parallel
    tasks = {
        "positive": {"papers": positive_papers, "title": "### Positive Viewpoint"},
        "negative": {"papers": negative_papers, "title": "### Negative Viewpoint"},
        "neutral": {"papers": neutral_papers, "title": "### Neutral Viewpoint"}
    }

    results = {}
    
    # Start parallel execution
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                contextvars.copy_context().run,
                summary_tool,
                info["papers"], state["original_query"]
            ): key
            for key, info in tasks.items()
        }
        
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    summary = (
        f"{tasks['positive']['title']}\n{results['positive']}\n\n"
        f"{tasks['negative']['title']}\n{results['negative']}\n\n"
        f"{tasks['neutral']['title']}\n{results['neutral']}"
    )
    
    return {"summary": summary}


def write_output_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Summary completed, report writing now in progress."})

    date      = state.get("date", datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
    path      = state.get("output_path", f"uploads/output/literature/{date}/result_{date}.md")
    raw_path = f"uploads/output/literature/{date}/result_{date}_raw.md"

    # Get the data from each stage
    raw       = state.get("search_results", [])
    t_filter  = state.get("title_filter", [])
    extracted = state.get("abstract_extract", [])
    summary   = state.get("summary", "None")

    # ── Compute screening-funnel numbers ──
    # Number kept at the title stage
    passed_title = len([p for p in t_filter if p.get("title_decision") == "relevant"])
    # Number kept at the abstract stage
    passed_abstract = len([p for p in extracted if p.get("abstract_decision") == "relevant"])

    # ── Section 1: search strategy ────────────────────────────────────────────
    pubmed_q = state.get("pubmed_query", "")
    queries_md = f"- {pubmed_q}" if pubmed_q else "None"

    strategy_md = f"""- **PubMed search**：{queries_md}"""

    # ── Section 2: literature screening funnel table (optimised) ──────────────────
    stats_md = f"""
| 篩選階段 (Screening Stage) | 文獻數量 (Paper Count) | 說明 (Description) |
| :--- | :--- | :--- |
| **1. 原始檢索 (Raw Search)** | {len(raw)} 篇 | PubMed 關鍵字擴展檢索總數 |
| **2. 標題初篩 (Title Filter)** | {passed_title} / {len(t_filter)} 篇 | 經大模型評估標題具相關性者 |
| **3. 摘要複篩 (Abstract Filter)** | {passed_abstract} / {passed_title} 篇 | 獲取真實摘要後，經二元相關性確認者 |
| **4. 最終萃取 (Final Extracted)** | {len(extracted)} 篇 | 成功完成結構化數據特徵萃取之黃金名單 |
"""

    # ── Section 4: literature scoring table (grouped by evidence level) ─────────
    direction_emoji = {"positive": "✅", "negative": "❌", "neutral": "⚪"}


    def make_table(papers: list[dict]) -> str:
        if not papers:
            return "_（無符合此條件之有效文獻）_"
        rows = []
        for i, p in enumerate(papers):
            # Truncate titles so the table does not blow up
            title     = p.get("title", "N/A")
            short_title = f"{title[:75]}..." if len(title) > 75 else title
            year      = p.get("year") or p.get("publication_year", "N/A")
            direction = p.get("direction", "neutral")
            emoji     = direction_emoji.get(direction, "⚪")
            urls      = p.get("pm_url", "N/A")
            
            # Build hyperlink format
            title_link = f"[{short_title}]({urls})" if urls != "N/A" else short_title
            
            rows.append(
                f"| {i+1} | {title_link}<br>_({year})_ "
                f"| {emoji} {direction} | {p.get("key_finding")} |"
                f"| {p.get("population")} | {p.get("exposure")}|{p.get("outcome")} | {p.get("study_design")} |"
                f"| {p.get("sample_size")} | {p.get("limitation")} |"
            )

        header = (
            "| # | 標題 (年份／連結) | 回答方向 | 核心生醫發現 | population | exposure | outcome | study_design | sample_size | limitation |\n"
            "|---|-----------------|----------|-------------|------------|----------|---------|-------------|-------------|-------------|"
        )
        return header + "\n" + "\n".join(rows)

    detailed_table_md = make_table(extracted)

    # ── Section 6: raw search result details ─────────────────────────────────────
    raw_md_rows = []
    for p in raw:
        t = p.get('title', 'N/A')
        url = p.get('pm_url', '')
        src = p.get('_source', p.get('source', 'pubmed'))
        lvl = p.get('_evidence_level', 'direct')
        yr = p.get('year') or p.get('publication_year', 'N/A')
        
        t_link = f"[{t}]({url})" if url else t
        raw_md_rows.append(f"- {t_link} `來源: {src}` `層級: {lvl}` | 年份: {yr}")
    
    raw_md = "\n".join(raw_md_rows) if raw_md_rows else "- （無原始檢索結果）"

    # ── Assemble the full Markdown report ──────────────────────────────────────────
    content = f"""# 文獻搜尋與生物醫學證據報告

**產生時間**：{date}
**原始研究問題**：{state['original_query']}

原始結果請至{raw_path}查看
---

## 1. 關鍵字擴展與搜尋策略
{strategy_md}

---

## 2. 篩選漏斗與文獻統計
{stats_md}

---

## 3. 根據文獻綜合回答
{summary}

---

## 4. 精選文獻特徵詳細列表
本列表僅包含通過【標題】與【摘要】雙重篩選，且成功進行結構化特徵萃取的黃金文獻：

{detailed_table_md}

---
"""
    raw_content = f"""# 文獻搜尋與生物醫學證據報告

**產生時間**：{date}
**原始研究問題**：{state['original_query']}
**原始搜尋數量**：共 {len(raw)} 篇 

篩選結果請至{path}查看

## 1. 關鍵字擴展與搜尋策略
{strategy_md}

---
## 2. 原始檢索結果總覽 (未篩選前明細)
{raw_md}

---
"""

    # Write the Markdown file
    write_file.invoke({"path": path, "content": content})
    write_file.invoke({"path": raw_path, "content": raw_content})

    if writer:
        writer({
            "status": "Report writing complete. Generating plots...",
            "output_file_path": f"uploads/output/literature/{date}"
        })

    return {
        "messages":    [AIMessage(content=f"查詢報告已成功儲存至：\n* Summary: `{path}`\n* Raw: `{raw_path}`")],
        "output_path": path,
    }

# ── Graph assembly ─────────────────────────────────────────────────────────────

def build_literature_graph():
    builder = StateGraph(LitPubState)

    # ==================== 1. Register nodes (Add Nodes) ====================
    builder.add_node("expand_query",        expand_query_node)
    builder.add_node("search_node",         search_node)
    builder.add_node("title_filter",        title_filter_node)
    builder.add_node("abstract_filter",     abstract_filter_node)
    builder.add_node("abstract_extract",    abstract_extract_node) 
    builder.add_node("summary",             summary_node)
    builder.add_node("write_output",        write_output_node)

    # ==================== 2. Wire the flow (Add Edges) ====================
    builder.add_edge(START, "expand_query")
    builder.add_edge("expand_query", "search_node")
    builder.add_edge("search_node",  "title_filter")
    builder.add_edge("title_filter",  "abstract_filter")
    builder.add_edge("abstract_filter",  "abstract_extract")
    builder.add_edge("abstract_extract", "summary")
    builder.add_edge("summary",      "write_output")
    builder.add_edge("write_output", END)

    return builder.compile()


literature_scoping = build_literature_graph()
