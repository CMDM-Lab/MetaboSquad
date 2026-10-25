"""
state.py - shared State definitions
"""

from __future__ import annotations
from typing import Annotated, Any, Literal, TypedDict
import operator
from langchain_core.messages import AnyMessage

# ── Shared message reducer (append-only) ───────────────────────────────────────
def add_messages(left: list, right: list) -> list:
    return left + right

# ── Main-graph State ──────────────────────────────────────────────────────────
class MainState(TypedDict, total=False):
    messages:       Annotated[list[AnyMessage], add_messages]
    files:          list[str]                         # File paths uploaded by the user
    original_query: str
    date:           str                               # Current timestamp (YYYY-MM-DD-HH-MM-SS)
    intent:         str                               # Classified intent
    task_plan:    list[dict]                            
    task_results: Annotated[list[dict], operator.add] # Send API needs operator.add
    
    # Intermediate results shared across nodes
    analysis_result: dict[str, Any]                   # Output of the analysis subgraph
    # Output of the plot_review subgraph. If it is not declared, LangGraph **silently drops**
    # it -- `plot_graph.py` does write review_result, yet it is missing from the return value
    # of `main_agent.invoke()`, so the structured_payload in `chat.py` is empty and the result
    # block is never built. As a knock-on effect `folder` is not persisted either (it hangs off
    # the result block), so after a refresh the physician sees empty "Files" and "Full report"
    # tabs even though the report is on disk.
    # Guarded by tests/test_structured_keys_declared.py (the rule covers all of
    # STRUCTURED_KEYS, not just this one).
    review_result: list[dict[str, Any]]
    # `sig_all` is the TRUE total of significant features (FDR < 0.05): named
    # metabolites plus bare m/z-only features, exactly the sum
    # `extract_significant_node` already computes
    # (`use_tool/pathway_analysis.py:122`, `graph/analysis_graph.py:114,134`).
    # `significant_metabolites` right below is a DIFFERENT, narrower count:
    # only the rows whose Feature label is not a pure m/z string, i.e. rows
    # with a compound name (`use_tool/pathway_analysis.py:109-120`). Both are
    # kept because they answer different questions — "how many features
    # cleared the FDR threshold" vs "how many of those got a name" — and
    # collapsing to one number silently drops whichever question the
    # physician did not ask. For a dataset keyed entirely by m/z (such as
    # the bundled lcms_table.csv), `significant_metabolites` alone reads
    # as "found nothing" when the true count is in the dozens.
    # Declared here for the same reason as `review_result` above: LangGraph
    # silently drops a subgraph channel this TypedDict does not declare.
    # `extract_significant_node` computed `sig_all` all along
    # (`graph/analysis_graph.py:134`); it never reached `chat.py`'s
    # `STRUCTURED_KEYS` because of exactly that gap.
    # Guarded by tests/test_structured_keys_declared.py.
    sig_all: list[str]
    significant_metabolites: list[str]                # Output of extract_significant
    id_mapping_result:  dict[str, Any]                # PubChem lookup results
    literature_result: dict[str, Any]                 # Literature search results
    literature_snowball_result: dict[str, Any]        # Literature search results

# ── Analysis Subgraph State ───────────────────────────────────────────────────
class AnalysisState(TypedDict, total=False):
    messages:       Annotated[list[AnyMessage], add_messages]
    date:           str
    files:          list[str]
    original_query: str   
    group_name: str
    paired: bool
    label_is_continuous: bool
    mode: Literal["positive", "negative"]
    analysis_result: dict[str, Any]
    primary_csv_path: str
    mummichog_peak_table: str | None
    result_dir: str
    sig_all: list[str]
    significant_metabolites: list[str]
    pubchem_result:  dict[str, Any]
    pubchem_table_text: str | None
    pubchem_kegg_mapping: dict
    pathway_result:  dict[str, Any] | None
    mummichog_result: dict | None
    output_path:    str
    all_detected_features: list[str]  
    metabolite_scores:    list[dict]  
    output_root:          str         

# ── Plot Review Subgraph State ────────────────────────────────────────────────
class PlotReviewState(TypedDict, total=False):
    messages:       Annotated[list[AnyMessage], add_messages]
    original_query: str
    files:          list[str]
    review_result:  list[dict[str, Any]]
    figure_compliance_check: list[dict[str, Any]]
    output_path:     str

# ── Id Mapping Subgraph State ────────────────────────────────────────────────────
class IdMappingState(TypedDict, total=False):
    messages:       Annotated[list[AnyMessage], add_messages]
    original_query: str   
    metabolites:    list[str]         
    id_mapping_result: dict[str, Any]
    output_path:     str           
    
# ── Literature Subgraph State ─────────────────────────────────────────────────
class LitPubState(TypedDict, total=False):
    messages:        Annotated[list[AnyMessage], add_messages]
    date:            str
    original_query:  str
    pubmed_query: str
    search_results:  list[dict]
    title_filter:       list[dict]        
    abstract_filter:    list[dict]
    abstract_extract:   list[dict]
    summary:         str
    output_path:     str
