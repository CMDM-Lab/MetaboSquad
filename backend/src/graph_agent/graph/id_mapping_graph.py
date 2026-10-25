import os
from datetime import datetime

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from src.graph_agent.state import IdMappingState
from src.graph_agent.tools import pubchem_id_mapping, cleaned_metabolites, write_file
from dotenv import load_dotenv
load_dotenv()


# ════════════════════════════════════════════════════════════════════════════
# PubChem Subgraph
# ════════════════════════════════════════════════════════════════════════════
def cleaned_metabolites_node(state: IdMappingState) -> dict:
    """Expand the user's question into several metabolite combinations"""
    query = state["original_query"]
    queries: list[str] = cleaned_metabolites(query)
    return {"metabolites": queries}

def pubchem_node(state: IdMappingState, config: RunnableConfig) -> dict:
    """Look up information for the metabolites in state.metabolites"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "ID mapping in progress."})
    metabolites = state.get("metabolites", [])
    date      = state.get("date", datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
    folder_relative_path = f"uploads/output/id_mapping/{date}"
    os.makedirs(os.path.abspath(folder_relative_path), exist_ok=True)
    path = f"{folder_relative_path}/result_{date}.md"

    if not metabolites:
        return {
            "messages":     [AIMessage(content="The name of the metabolite was not provided.")],
            "id_mapping_result": {},
        }
    data_list: dict = pubchem_id_mapping.invoke({"metabolite_names": metabolites})
    table_rows = []
    
    
    for item in data_list:
        name = item.get("query", "Unknown")
        view = item.get("pubchem_pug_view")
        safe_info = view if isinstance(view, dict) else {}

        cid = safe_info.get('cid', 'N/A')
        formula_list = safe_info.get('molecular_formulas', [])
        formula = ", ".join(formula_list) if formula_list else 'N/A'
        weight_list = safe_info.get('molecular_weight', [])
        weight = ", ".join(weight_list) if weight_list else 'N/A'
        iupac_list = safe_info.get('iupac_names', [])
        iupac = ", ".join(iupac_list) if iupac_list else 'N/A'
        inch_list = safe_info.get('inchkeys', [])
        inch = ", ".join(inch_list) if inch_list else 'N/A'
        smiles_list = safe_info.get('smiles', [])
        smiles = ", ".join(smiles_list) if smiles_list else 'N/A'
        
        def format_ids(key):
            id_list = safe_info.get(key, [])
            if isinstance(id_list, list) and id_list:
                links = []
                for x in id_list:
                    id_val = x.get("id", "")
                    url_val = x.get("url", "")
                    if id_val:
                        links.append(f"[{id_val}]({url_val})" if url_val else id_val)
                return ", ".join(list(dict.fromkeys(links))) if links else 'N/A'
            return 'N/A'

        kegg = format_ids("kegg")
        hmdb = format_ids("hmdb")
        chebi = format_ids("chebi")
        drugbank = format_ids("drugbank")
        # ────────────────────────────────────────────────────────

        url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid != 'N/A' else ""
        link = f"[PubChem]({url})" if url else "N/A"
        
        row = f"| {name} | {cid} | {formula} | {weight} | {iupac} | {inch} | {smiles} | {kegg} | {hmdb} | {chebi} | {drugbank} | {link} |"
        table_rows.append(row)

    rows_text = "\n".join(table_rows)
    pubchem_section = f"""
## PubChem 代謝物詳細資料彙整

| name | CID | Molecular Formula | Molecular Weight | IUPAC name | InChIKey | SMILES | KEGG | HMDB | ChEBI | DrugBank | link |
|--------|-----|-----------------|-------------------|-----------|--------|----------|-------|------|------|----------|--------|
{rows_text}
"""

    write_file.invoke({"path": path, "content": pubchem_section})
    

    if writer:
        writer({
            "status": "Report writing complete",
            "output_file_path": folder_relative_path 
        })
        
    return {
        "messages":     [AIMessage(content=f"Search result:\n\n{data_list}")],
        "id_mapping_result": data_list,
    }


def build_id_mapping_graph():
    builder = StateGraph(IdMappingState)
    builder.add_node("clean", cleaned_metabolites_node)
    builder.add_node("pubchem", pubchem_node)
    builder.add_edge(START, "clean")
    builder.add_edge("clean", "pubchem")
    builder.add_edge("pubchem", END)
    return builder.compile()


id_mapping_graph = build_id_mapping_graph()

