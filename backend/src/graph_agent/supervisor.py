"""
supervisor.py - main-graph Supervisor (intent classification + routing)

Routing targets:
  literature_search    → literature_graph
  analysis             → analysis_graph
  plot_review          → plot_review_graph
  id_mapping           → id_mapping_graph
  direct               → direct_response_node (answers directly)
"""

from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send
# from langgraph.constants import Send
from .state import MainState
from langchain_core.runnables import RunnableConfig
from .graph.literature_scoping_only_pubmed import literature_scoping

from .graph.analysis_graph import analysis_graph
from .graph.id_mapping_graph import id_mapping_graph
from .graph.plot_graph import plot_review_graph
from dotenv import load_dotenv
load_dotenv()

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

# ===== Ollama =====
# from .graph.literature_gemma import literature_gemma
# pip install langchain-ollama
# from langchain_ollama import ChatOllama 
# llm = ChatOllama(
#     model="gemma4:26b",
#     temperature=0,
#     base_url="http://localhost:11434",
#     num_ctx=8192,          # or 16384
#     keep_alive="30m",      # avoid being unloaded between nodes
#     client_kwargs={"timeout": 300.0},  # 5-minute timeout to avoid hanging forever
# )

class Task(BaseModel):
    intent: str = Field(
        ..., 
        description=(
            "Task Name. Must be one of the following:"
            "'literature_search', 'analysis', "
            "'plot_review', 'id_mapping', 'direct'"
        )
    )
    query: str = Field(
        ..., 
        description="The original text description entered by the user for the task is completely preserved without any modification or rewriting."
    )

class IntentResponse(BaseModel):
    """Task list of the final structured output"""
    tasks: List[Task] = Field(..., description="A list of tasks that need to be performed.")

# ── Intent classification prompt ──────────────────────────────────────────────
INTENT_SYSTEM = """
You are the Intent Classifier for a Metabolomics Research Assistant.
Based on the user's message, determine the list of tasks that need to be executed.

You must strictly adhere to the following mapping rules for task names (intent):

"literature_search" (Broad Literature Search Mode):
- Criteria: The user wants to find background literature for a specific "scientific question", "field", or "multiple keywords".
-Keyword Examples: look up literature, find information, related research, search, relationship between A and B.
- Example: {"intent": "literature_search", "query": "Relationship between benzoic acid and lung cancer"}
- Example: {"intent": "literature_search", "query": "請你幫我搜尋重金屬與癌症發生的相關性文獻"}

"analysis":
- Criteria: The user mentions "data analysis, peak table, CSV analysis, statistical analysis" AND provides a file path.

"plot_review":
- Criteria: The user mentions "review image, chart review, image quality, whether it meets publication standards" AND provides an image path.

"id_mapping":
- Criteria: The user mentions "metabolite information, PubChem, metabolite ID, query metabolite" AND explicitly mentions the specific metabolite name they want to find.

"direct":
- Criteria: General conversation, small talk, greetings, or anything that does not belong to the above categories, or simply asking about capabilities.

【Notes】
- All tasks must be wrapped inside a tasks list.
- For the query field, please "completely copy" the user's original input related to that task. Do not omit any IDs, digits, or words, as subsequent nodes require this information for precise parsing.

"""

# ── Nodes ─────────────────────────────────────────────────────────────────────
def _extract_last_user_message(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            content = m.content
        elif isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content", "")
        else:
            continue
        
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
    return ""

def input_verifier_node(state: MainState) -> dict:
    """Preprocessing node: check for files the query does not mention, and fix or enrich the original input query."""
    files = state.get("files", [])
    messages = state.get("messages", [])
    last_user_msg = _extract_last_user_message(messages)

    # Check whether the prompt already contains a file path / keyword
    has_file_mention = any(f in last_user_msg for f in files) or any(
        kw in last_user_msg for kw in ["csv", "png", "jpg"]
    )

    updated_query = last_user_msg

    # If files were uploaded but the message does not mention them at all, add the file info automatically
    if files and not has_file_mention:
        file_str = ", ".join(files)
        updated_query = (
            f"{last_user_msg}\n(系統自動補充上傳檔案路徑: {file_str})"
        )

    return {
        "original_query": updated_query,
    }
    
def _correct_misclassification(task: dict, files: list = None) -> dict:
    """Post-hoc correction: fix fuzzy-boundary cases common in LLM classification, and missing files"""
    intent = task.get("intent")
    query = task.get("query", "").lower()
    files = files or []

    # Correction case 0: intent is plot review or data analysis but no file was provided -> force direct
    if intent in ["plot_review", "analysis"] and not files:
        task["intent"] = "direct"
        return task

    # Correction case 1: a single-metabolite lookup misclassified as a literature search
    # When intent is literature_search but the query contains common metabolite-attribute keywords and no literature keywords
    metabolite_keywords = ["詳細資料", "pubchem", "cas", "cid", "結構", "代謝物資訊"]
    lit_keywords = ["論文", "文獻", "研究", "paper", "journal", "幾篇", "相關性"]

    if intent == "literature_search":
        has_meta_kw = any(kw in query for kw in metabolite_keywords)
        has_lit_kw = any(kw in query for kw in lit_keywords)

        # Only metabolite keywords, no paper/literature keywords -> force-correct to id_mapping
        if has_meta_kw and not has_lit_kw:
            task["intent"] = "id_mapping"

    return task


def supervisor_node(state: MainState) -> dict:
    """Decide the task type and route accordingly"""
    date = state.get("date") or datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    last_user = state.get("original_query","")
    files = state.get("files", [])
    structured_llm = llm.with_structured_output(IntentResponse)

    try:
        res_obj = structured_llm.invoke(
            [
                SystemMessage(content=INTENT_SYSTEM),
                HumanMessage(content=last_user),
            ]
        )
        tasks = [task.model_dump() for task in res_obj.tasks]

        # 🎯 Apply code-level task correction
        tasks = [_correct_misclassification(task, files=files) for task in tasks]

    except Exception as e:
        print(f"結構化輸出解析失敗: {e}")
        tasks = [{"intent": "direct", "query": last_user}]

    return {
        "task_plan": tasks,
        "date": date,
        "intent": tasks[0]["intent"] if len(tasks) == 1 else "compound",
    }


def supervisor_router(state: MainState):
    """Based on the task_plan produced by supervisor_node, go to a single node or fan out dynamically in parallel (Send API)."""
    tasks = state.get("task_plan", [])

    # Case A: multiple tasks -> use the Send API to dispatch them in parallel to execute_single_task
    if len(tasks) > 1:
        return [
            Send("execute_single_task", {**state, "current_task": task})
            for task in tasks
        ]

    # Case B: single task -> return the target node name (string)
    if len(tasks) == 1:
        intent = tasks[0].get("intent", "direct")
        valid = {
            "literature_search",
            "analysis",
            "plot_review",
            "id_mapping",
            "direct",
        }
        return intent if intent in valid else "direct"

    # Fallback
    return "direct"


# System prompt for `direct_response_node`. It is a module constant so that
# tests/test_scope_guardrail.py can assert the prompt **content** precisely -- when it
# was inlined in the function, the test could only grab the whole function with
# inspect.getsource, which also matched comments and the docstring, so "small talk"
# appearing in explanatory text was misread as "the prompt still invites small talk".
DIRECT_RESPONSE_SYSTEM = (
    "You are a Metabolomics Research Assistant. Please respond to the user's questions in Traditional Chinese or English.\n"
    "\n"
    "## Scope (strict)\n"
    "You only help with:\n"
    "1. Metabolomics — metabolites, peak tables, LC-MS/GC-MS data, experimental design.\n"
    "2. Metabolic pathways — pathway analysis, enrichment, KEGG/HMDB, biological interpretation.\n"
    "3. Statistical methods for the above — normalisation, univariate/multivariate tests, "
    "multiple-testing correction, and how to choose between them.\n"
    "4. Checking whether a figure or a result is correct and reasonable — publication standards, "
    "whether a statistical claim is supported by the data.\n"
    "\n"
    "Anything outside those four areas is out of scope: general chit-chat, greetings beyond a "
    "one-line reply, opinions, jokes, news, coding help unrelated to metabolomics, medical advice "
    "for an individual patient, or other scientific fields. For an out-of-scope request, decline "
    "briefly and politely in one or two sentences, then redirect the user by naming what you can "
    "do instead. Do not answer the out-of-scope question even partially, and do not apologise at "
    "length. Never invite the user to chat about unrelated topics.\n"
    "\n"
    "## Capabilities\n"
    "If the user asks what you can do, or whether you can perform the following functions, please introduce these features:\n"
    "1. Literature Search (PubMed): Please provide the question you want to know, the field you want to search, or a specific piece of literature you want to understand.\n"
    "2. Data Analysis (MetaboAnalystR): Please provide the group names, whether the grouping consists of the same samples with different treatments, and whether it is a discrete grouping.\n"
    "3. Image Review (Scientific Publication Standards): Please provide the image.\n"
    "4. Metabolite Query (PubChem): Please provide the name of the metabolite you want to search for.\n"
)


def direct_response_node(state: MainState) -> dict:
    """Handle general conversation (responses that need no tool).

    This node is where every message not routed to a tool lands, so putting the
    scope guardrail here covers everything: `_correct_misclassification` demotes
    analysis/plot_review without files to direct, and `INTENT_SYSTEM` explicitly
    classifies small talk and greetings as direct. No extra classification call is
    needed at the API layer (that would cost one more LLM round trip).

    The original prompt was only a self-introduction ("You are a Metabolomics Research
    Assistant" plus four capabilities) with no boundaries, so it would happily answer
    about weather, mood or coding. Guarded by tests/test_scope_guardrail.py.
    """
    resp = llm.invoke([
        SystemMessage(content=DIRECT_RESPONSE_SYSTEM),
        *state.get("messages", []),
    ])
    return {"messages": [AIMessage(content=resp.content)]}

def execute_single_task(state: MainState, config: RunnableConfig) -> dict:
    task    = state.get("current_task", {})
    intent  = task.get("intent", "direct")
    query   = task.get("query", "")
    msg     = [*state.get("messages", []), HumanMessage(content=query)]
    patched = {**state, "messages": msg}

    wrapper_map = {
        "literature_search":   lit_wrapper,
        "id_mapping":          id_mapping_wrapper,
        "analysis":            analysis_wrapper,
        "plot_review":         plot_review_wrapper,
        "direct":              direct_response_node,
    }
    try:
        # Pass config through
        result = wrapper_map.get(intent, direct_response_node)(patched, config)
        ai_msg = next(
            (m for m in reversed(result.get("messages", [])) if isinstance(m, AIMessage)),
            AIMessage(content="（無結果）")
        )
    except Exception as e:
        ai_msg = AIMessage(content=f"（{intent} 執行失敗：{e}）")

    return {"task_results": [{"intent": intent, "query": query, "message": ai_msg}]}


def synthesize_node(state: MainState) -> dict:
    """Merge the results of all tasks into one fluent reply"""
    results  = state.get("task_results", [])
    combined = "\n\n".join(
        f"【{r['intent']}｜{r['query']}】\n{r['message'].content}"
        for r in results
    )
    resp = llm.invoke([
        SystemMessage(content="Please combine the results of the following tasks. Please respond to the user's questions in the same language they used to ask."),
        HumanMessage(content=combined),
    ])
    return {"messages": [AIMessage(content=resp.content)]}

# ── State bridges (conversion between subgraph state and main-graph state) ─────

def to_lit_state(state: MainState) -> dict:
    """MainState → LitState"""

    return {
        "messages":       state.get("messages", []),
        "date":           state.get("date", ""),
        "original_query": state.get("original_query",""),
        "search_results": [],
    }


def from_lit_state(state: dict) -> dict:
    """Merge LitState results back into MainState"""
    text_extract = state.get("text_extract") or state.get("abstract_extract", [])
    return {
        "messages":        state.get("messages", []),
        "literature_result": {
            "output_path":     state.get("output_path", ""),
            "summary":         state.get("summary", ""),
            "text_extract":    text_extract,
            "abstract_extract": state.get("abstract_extract", []),
            "evidence_check":  state.get("evidence_check", {}),
        },
    }


def to_analysis_state(state: MainState) -> dict:
    """MainState → AnalysisState"""

    return {
        "messages":            state.get("messages", []),
        "files":               state.get("files", []),
        "date":                state.get("date", ""),
        "original_query":      state.get("original_query",""),
    }


def from_analysis_state(state: dict) -> dict:
    """AnalysisState → MainState"""
    return {
        "messages":               state.get("messages", []),
        "analysis_result":        state.get("analysis_result", {}),
        "sig_all":                state.get("sig_all", []),
        "significant_metabolites": state.get("significant_metabolites", []),
        "id_mapping_result":         state.get("id_mapping_result", {}),
    }


def to_plot_state(state: MainState) -> dict:
    return {
        "messages":            state.get("messages", []),
        "files":               state.get("files", []),
        "original_query":      state.get("original_query",""),
    }


def from_plot_state(state: dict) -> dict:
    return {
        "messages": state.get("messages", []),
        "review_result":state.get("review_result", {}),
        }


def to_mapping_state(state: MainState) -> dict:
    # last_user = _extract_last_user_message(state.get("messages", []))

    return {
        "messages":       state.get("messages", []),
        "original_query": state.get("original_query",""),
    }


def from_mapping_state(state: dict) -> dict:
    return {
        "messages":     state.get("messages", []),
        "id_mapping_result": state.get("id_mapping_result", {}),
    }

# ── Wrap subgraphs as main-graph nodes ────────────────────────────────────────

def lit_wrapper(state: MainState, config: RunnableConfig) -> dict:
    result = literature_scoping.invoke(to_lit_state(state), config=config)
    return from_lit_state(result)

def analysis_wrapper(state: MainState, config: RunnableConfig) -> dict:
    result = analysis_graph.invoke(to_analysis_state(state), config=config)
    return from_analysis_state(result)


def plot_review_wrapper(state: MainState, config: RunnableConfig) -> dict:
    result = plot_review_graph.invoke(to_plot_state(state), config=config)
    return from_plot_state(result)

def id_mapping_wrapper(state: MainState, config: RunnableConfig) -> dict:
    result = id_mapping_graph.invoke(to_mapping_state(state), config=config)
    return from_mapping_state(result)


# ── Main graph assembly ────────────────────────────────────────────────────────
def build_main_graph(store=None, checkpointer=None):
    # Only create new default instances at call time if the caller passed no custom components
    if store is None:
        store = InMemoryStore()
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(MainState)
    builder.add_node("input_verifier",        input_verifier_node) 
    builder.add_node("supervisor",            supervisor_node)
    builder.add_node("direct",                direct_response_node)
    builder.add_node("literature_search",     lit_wrapper)
    builder.add_node("analysis",              analysis_wrapper)
    builder.add_node("plot_review",           plot_review_wrapper)
    builder.add_node("id_mapping",            id_mapping_wrapper)
    # builder.add_node("fan_out",               fan_out)            
    builder.add_node("execute_single_task",   execute_single_task)
    builder.add_node("synthesize",            synthesize_node)    

    # builder.add_edge(START, "supervisor")
    builder.add_edge(START, "input_verifier")
    builder.add_edge("input_verifier", "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        supervisor_router,  
        {
            "literature_search": "literature_search",
            "analysis": "analysis",
            "plot_review": "plot_review",
            "id_mapping": "id_mapping",
            "direct": "direct",
            "execute_single_task": "execute_single_task", 
        },
    )               

    # 4. Multi-task parallel fan-in: after every execute_single_task finishes, go to synthesize
    builder.add_edge("execute_single_task", "synthesize")
    builder.add_edge("synthesize", END)

    # 5. Single-task route ends directly
    for node in [
        "direct",
        "literature_search",
        "analysis",
        "plot_review",
        "id_mapping",
    ]:
        builder.add_edge(node, END)
        
    return builder.compile(checkpointer=checkpointer, store=store)


# Default main graph with memory
# main_graph = build_main_graph()



