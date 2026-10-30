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

    strategy_md = f"""- **PubMed search**: {queries_md}"""

    # ── Section 2: literature screening funnel table (optimised) ──────────────────
    stats_md = f"""
| Screening Stage | Paper Count | Description |
| :--- | :--- | :--- |
| **1. Raw Search** | {len(raw)} papers | Total records retrieved by the expanded PubMed keyword search |
| **2. Title Filter** | {passed_title} / {len(t_filter)} papers | Papers whose titles the LLM judged relevant |
| **3. Abstract Filter** | {passed_abstract} / {passed_title} papers | Papers confirmed relevant by a binary check on the retrieved abstract |
| **4. Final Extracted** | {len(extracted)} papers | Final set with successful structured data extraction |
"""

    # ── Section 4: literature scoring table (grouped by evidence level) ─────────
    direction_emoji = {"positive": "✅", "negative": "❌", "neutral": "⚪"}


    def make_table(papers: list[dict]) -> str:
        if not papers:
            return "_(No eligible papers meet these criteria)_"
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
            "| # | Title (Year / Link) | Direction | Key Biomedical Finding | population | exposure | outcome | study_design | sample_size | limitation |\n"
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
        raw_md_rows.append(f"- {t_link} `Source: {src}` `Level: {lvl}` | Year: {yr}")
    
    raw_md = "\n".join(raw_md_rows) if raw_md_rows else "- (No raw search results)"

    # ── Assemble the full Markdown report ──────────────────────────────────────────
    content = f"""# Literature Search and Biomedical Evidence Report

**Generated at**: {date}
**Original research question**: {state['original_query']}

See {raw_path} for the raw results
---

## 1. Keyword Expansion and Search Strategy
{strategy_md}

---

## 2. Screening Funnel and Paper Counts
{stats_md}

---

## 3. Evidence-Based Synthesis
{summary}

---

## 4. Detailed Characteristics of Selected Papers
This list includes only the papers that passed both the title and the abstract screening and had their characteristics successfully extracted into structured data:

{detailed_table_md}

---
"""
    raw_content = f"""# Literature Search and Biomedical Evidence Report

**Generated at**: {date}
**Original research question**: {state['original_query']}
**Raw search count**: {len(raw)} papers in total

See {path} for the screened results

## 1. Keyword Expansion and Search Strategy
{strategy_md}

---
## 2. Overview of Raw Search Results (Before Screening)
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
        "messages":    [AIMessage(content=f"Literature reports saved to:\n* Summary: `{path}`\n* Raw: `{raw_path}`")],
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
