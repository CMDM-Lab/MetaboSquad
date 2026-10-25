from __future__ import annotations
import json
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from src.graph_agent.pydantic_models import SearchPubmed, Metadata

from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
load_dotenv()

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

# ===== Ollama =====
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

def query_expansion(question: str) -> dict:
    """
    Expand the user's question into several sets of search keywords, and decide whether full-text search and an indirect-evidence strategy are needed.
    """
    system_prompt = (
        "You are a biomedical literature search specialist.\n\n"
        "Your task is to analyze a research question and generate structured search query "
        "with an indirect evidence strategy.\n\n"

        "Instructions for pubmed_query:\n"
        "1. Identify the key biomedical concepts (exposure, outcome, population).\n"
        "2. For each concept, list synonyms and MeSH terms.\n"
        "3. Combine synonyms within a concept using OR.\n"
        "4. Combine distinct concepts using AND.\n"
        "5. CRITICAL: Do NOT use double quotes anywhere inside the pubmed_query string.\n"
        "for example: (smoking OR tobacco OR cigarette) AND (oral cancer OR oral carcinoma OR OSCC),"
    )


    structured_llm = llm.with_structured_output(SearchPubmed)

    resp = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=question),
    ])
    return resp
 
def cleaned_metabolites(query: str) -> list[str]:
    """
    Expand the metabolites the user's question wants to search for into a list.
    """
    resp = llm.invoke([
        SystemMessage(content=(
            "Given a question, extract the names of metabolites or chemicals from the input."
            "Change the metabolites or chemicals name into English if it is not English."
            "Return ONLY a JSON array of strings, no explanation."
            'for example: ["oxaloacetate", "succinate"]'
            "Do NOT use markdown code fences (no ```json)"
        )),
        HumanMessage(content=query),
    ])
    queries = json.loads(resp.content)
    return queries  


def extract_metadata(query: str) -> dict:
    """
    Extract the file characteristics mentioned in the user's question.
    """
    structured_llm = llm.with_structured_output(Metadata)

    resp = structured_llm.invoke([
        SystemMessage(content=(
    "You are an expert assistant specializing in metabolomics data analysis.\n"
    "Your task is to analyze the user's query and extract key study design metadata according to the provided schema.\n"
    "Carefully infer the values based on the context of the metabolomics analysis."
    "no explanation"
    'for example: {"group_name":"group","paired":false,"label_is_continuous":false}'
        )),
        HumanMessage(content=query),
    ])

    return resp

@tool
def write_file(path: str, content: str) -> str:
    """Write the content to the path, or create the directory if it does not exist. Send back an acknowledgment message."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"檔案已儲存至 {path}"


@tool
def edit_file(path: str, append_content: str) -> str:
    """Append content to the end of an existing file. Create the file if it does not exist."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + append_content)
    return f"✅ 內容已追加至 {path}"

@tool
def read_file(path: str, content: str) -> str:
    """Write content to path, creating the directory if it does not exist. Return a confirmation message."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ 檔案已儲存至 {path}"

# ════════════════════════════════════════════════════════════════════════════
# Tool list (for convenient import by other modules)
# ════════════════════════════════════════════════════════════════════════════
from src.graph_agent.use_tool.search import search_pubmed, search_abstract
from src.graph_agent.use_tool.extract_significant import extract_significant
from src.graph_agent.use_tool.pubchem_id_mapping import pubchem_id_mapping
from src.graph_agent.use_tool.code import recommend_and_analysis
from src.graph_agent.use_tool.pathway_analysis import mummichog_analysis, map_names_to_kegg, run_ora_analysis, run_gsea_prerank, extract_significant
from src.graph_agent.use_tool.literature_add import (
    title_filter_tool, abstract_filter_tool, abstract_extract, 
    summary_tool,
)
LITERATURE_TOOLS = [search_pubmed, search_abstract, write_file, edit_file, title_filter_tool, abstract_filter_tool, abstract_extract, summary_tool]
ANALYSIS_TOOLS   = [recommend_and_analysis, mummichog_analysis, map_names_to_kegg, run_ora_analysis, run_gsea_prerank, extract_significant, extract_significant, write_file, edit_file]
PUBCHEM_TOOLS    = [pubchem_id_mapping, write_file, edit_file]

# Changed: use the object's name attribute if it has one, otherwise the function's original __name__
ALL_TOOLS = list({
    (t.name if hasattr(t, "name") else t.__name__): t 
    for t in LITERATURE_TOOLS + ANALYSIS_TOOLS + PUBCHEM_TOOLS
}.values())
