from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from src.graph_agent.state import LitPubState
from datetime import datetime
from src.graph_agent.use_tool.gemma_tool import (
    query_expansion_gemma, search_pubmed_gemma, search_abstract_gemma, title_filter_tool_gemma, 
    abstract_filter_tool_gemma, abstract_extract_gemma, write_file, summary_tool_gemma)

def expand_query_node(state: LitPubState, config: RunnableConfig) -> dict:
    query = state["original_query"]
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "expand_query"})

    result = query_expansion_gemma(query)
    return {"pubmed_query": result.pubmed_query}


def search_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Now searching in progress."})

    query = state["pubmed_query"]
    results = search_pubmed_gemma(query)
    return {"search_results": results}


def title_filter_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer(
            {"status": "Merge complete, now title filtering in progress."}
        )

    papers = state.get("search_results", [])
    chunk_size = 5
    chunks = [
        papers[i : i + chunk_size] for i in range(0, len(papers), chunk_size)
    ]

    ranked = []
    for chunk in chunks:
        title_filter_chunk = title_filter_tool_gemma(
            chunk, state["original_query"]
        )
        ranked.extend(title_filter_chunk)

    return {"title_filter": ranked}


def abstract_filter_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer(
            {
                "status": "Title filtering complete, now abstract filtering in progress."
            }
        )

    title_filter_results = state.get("title_filter", [])
    relevant_papers = [
        p
        for p in title_filter_results
        if p.get("title_decision") == "relevant"
    ]

    if not relevant_papers:
        return {"abstract_filter": []}

    pubmed_ids = [p.get("pmid") for p in relevant_papers if p.get("pmid")]
    abstract_map = {}

    if pubmed_ids:
        pubmed_data = search_abstract_gemma(pubmed_ids)
        for item in pubmed_data:
            if item.get("pmid"):
                abstract_map[str(item["pmid"])] = item["abstract"]

    for paper in relevant_papers:
        pmid = str(paper.get("pmid", ""))
        paper["abstract"] = abstract_map.get(pmid, "N/A")

    chunk_size = 5
    chunks = [
        relevant_papers[i : i + chunk_size]
        for i in range(0, len(relevant_papers), chunk_size)
    ]

    ranked = []
    for chunk in chunks:
        abstract_filter_chunk = abstract_filter_tool_gemma(
            chunk, state["original_query"]
        )
        ranked.extend(abstract_filter_chunk)

    return {"abstract_filter": ranked}


def abstract_extract_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer(
            {
                "status": "Abstract filtering complete, now extracting structured data."
            }
        )

    abstract_filter = state.get("abstract_filter", [])
    relevant_papers = [
        p
        for p in abstract_filter
        if p.get("abstract_decision") == "relevant"
    ]

    chunk_size = 5
    chunks = [
        relevant_papers[i : i + chunk_size]
        for i in range(0, len(relevant_papers), chunk_size)
    ]

    extracted = []
    for chunk in chunks:
        abstract_extract_chunk = abstract_extract_gemma(
            chunk, state["original_query"]
        )
        extracted.extend(abstract_extract_chunk)

    for p in extracted:
        p["text_source"] = "abstract_structured"

    return {"abstract_extract": extracted}


def summary_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer(
            {
                "status": "Literature search completed, summary now in progress."
            }
        )

    all_extracted_papers = state.get("abstract_extract", [])
    positive_papers, negative_papers, neutral_papers = [], [], []

    for p in all_extracted_papers:
        direction = str(p.get("direction", "")).lower().strip()
        if "positive" in direction:
            positive_papers.append(p)
        elif "negative" in direction:
            negative_papers.append(p)
        else:
            neutral_papers.append(p)

    tasks = {
        "positive": {
            "papers": positive_papers,
            "title": "### Positive Viewpoint",
        },
        "negative": {
            "papers": negative_papers,
            "title": "### Negative Viewpoint",
        },
        "neutral": {
            "papers": neutral_papers,
            "title": "### Neutral Viewpoint",
        },
    }

    results = {}
    for key, task_data in tasks.items():
        results[key] = summary_tool_gemma(
            task_data["papers"], state["original_query"]
        )

    summary = (
        f"{tasks['positive']['title']}\n{results['positive']}\n\n"
        f"{tasks['negative']['title']}\n{results['negative']}\n\n"
        f"{tasks['neutral']['title']}\n{results['neutral']}"
    )

    return {"summary": summary}


def write_output_node(state: LitPubState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer(
            {
                "status": "Summary completed, report writing now in progress."
            }
        )

    date = state.get(
        "date", datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    )
    path = state.get(
        "output_path",
        f"uploads/output/literature/{date}/result_{date}.md",
    )
    raw_path = f"uploads/output/literature/{date}/result_{date}_raw.md"

    raw = state.get("search_results", [])
    t_filter = state.get("title_filter", [])
    extracted = state.get("abstract_extract", [])
    summary = state.get("summary", "None")

    passed_title = len(
        [p for p in t_filter if p.get("title_decision") == "relevant"]
    )
    passed_abstract = len(
        [p for p in extracted if p.get("abstract_decision") == "relevant"]
    )

    pubmed_q = state.get("pubmed_query", "")
    strategy_md = f"- **PubMed search**: {pubmed_q if pubmed_q else 'None'}"

    stats_md = f"""
| Screening Stage | Paper Count | Description |
| :--- | :--- | :--- |
| **1. Raw Search** | {len(raw)} papers | Total records retrieved by the expanded PubMed keyword search |
| **2. Title Filter** | {passed_title} / {len(t_filter)} papers | Papers whose titles the LLM judged relevant |
| **3. Abstract Filter** | {passed_abstract} / {passed_title} papers | Papers confirmed relevant by a binary check on the retrieved abstract |
| **4. Final Extracted** | {len(extracted)} papers | Final set with successful structured data extraction |
"""

    direction_emoji = {"positive": "✅", "negative": "❌", "neutral": "⚪"}

    def make_table(papers: list[dict]) -> str:
        if not papers:
            return "_(No eligible papers meet these criteria)_"
        rows = []
        for i, p in enumerate(papers):
            title = p.get("title", "N/A")
            short_title = f"{title[:75]}..." if len(title) > 75 else title
            year = p.get("year") or p.get("publication_year", "N/A")
            direction = p.get("direction", "neutral")
            emoji = direction_emoji.get(direction, "⚪")
            urls = p.get("pm_url", "N/A")

            title_link = (
                f"[{short_title}]({urls})" if urls != "N/A" else short_title
            )

            key_find = p.get("key_finding", "")


            rows.append(
                f"| {i+1} | {title_link}<br>_({year})_ | {emoji} {direction} | {key_find} |"
            )

        header = (
            "| # | Title (Year / Link) | Direction | Key Biomedical Finding |\n"
            "|---|-----------------|----------|-------------|"
        )
        return header + "\n" + "\n".join(rows)

    detailed_table_md = make_table(extracted)

    raw_md_rows = []
    for p in raw:
        t = p.get("title", "N/A")
        url = p.get("pm_url", "")
        src = p.get("source", "pubmed")
        yr = p.get("year") or p.get("publication_year", "N/A")
        t_link = f"[{t}]({url})" if url else t
        raw_md_rows.append(f"- {t_link} `Source: {src}` | Year: {yr}")

    raw_md = (
        "\n".join(raw_md_rows) if raw_md_rows else "- (No raw search results)"
    )

    content = f"""# Literature Search and Biomedical Evidence Report (by gemma)

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
{detailed_table_md}

---
"""

    raw_content = f"""# Literature Search and Biomedical Evidence Report (Raw)

**Generated at**: {date}
**Original research question**: {state['original_query']}
**Raw search count**: {len(raw)} papers in total

See {path} for the screened results

## 1. Keyword Expansion and Search Strategy
{strategy_md}

---
## 2. Overview of Raw Search Results
{raw_md}

---
"""

    # Call the Python function directly to write the file
    write_file(path=path, content=content)
    write_file(path=raw_path, content=raw_content)

    if writer:
        writer(
            {
                "status": "Report writing complete.",
                "output_file_path": f"uploads/output/literature/{date}",
            }
        )

    return {
        "messages": [
            AIMessage(
                content=f"Literature reports saved to:\n* Summary: `{path}`\n* Raw: `{raw_path}`"
            )
        ],
        "output_path": path,
    }


# ── Graph construction and testing ───────────────────────────────────────────
def build_literature_graph():
    builder = StateGraph(LitPubState)

    builder.add_node("expand_query", expand_query_node)
    builder.add_node("search_node", search_node)
    builder.add_node("title_filter", title_filter_node)
    builder.add_node("abstract_filter", abstract_filter_node)
    builder.add_node("abstract_extract", abstract_extract_node)
    builder.add_node("summary", summary_node)
    builder.add_node("write_output", write_output_node)

    builder.add_edge(START, "expand_query")
    builder.add_edge("expand_query", "search_node")
    builder.add_edge("search_node", "title_filter")
    builder.add_edge("title_filter", "abstract_filter")
    builder.add_edge("abstract_filter", "abstract_extract")
    builder.add_edge("abstract_extract", "summary")
    builder.add_edge("summary", "write_output")
    builder.add_edge("write_output", END)

    return builder.compile()

literature_gemma = build_literature_graph()

# if __name__ == "__main__":
#     graph = build_literature_graph()
#     config: RunnableConfig = {
#         "configurable": {"thread_id": "test-2026-08-04-001"},
#         "writer": lambda msg: print(
#             f"📡 [Stream Status]: {msg.get('status', '')}"
#         ),
#     }

#     initial_state = {
#         "original_query": "Is non-HDL-cholesterol a better predictor of long-term outcome in patients after acute myocardial infarction compared to LDL-cholesterol?",
#         "date": datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
#     }

#     print("🏃‍♂️ Starting Subgraph test...")
#     for event in graph.stream(
#         initial_state, config=config, stream_mode="updates"
#     ):
#         for node_name, node_output in event.items():
#             print(f"✅ Node [{node_name}] finished")