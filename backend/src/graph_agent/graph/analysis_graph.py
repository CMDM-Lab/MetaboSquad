"""
analysis/graph.py - data-analysis subgraph

Flow:
  run_analysis (calls metaboanalystr)
    │
  extract_significant (extract significant metabolites)
    │
  run metabolic pathway analysis
    │
  save_significant (writes significant_{date}.md)
"""

import pandas as pd
import os
import json
from datetime import datetime

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END


from src.graph_agent.tools import write_file, pubchem_id_mapping, extract_metadata, mummichog_analysis, map_names_to_kegg, run_ora_analysis, run_gsea_prerank, extract_significant, recommend_and_analysis


# ── Models and state ─────────────────────────────────────────────────────────────────────
from src.graph_agent.pydantic_models import Metadata
from src.graph_agent.state import AnalysisState

# ── Nodes ─────────────────────────────────────────────────────────────────────
def extract_metadata_node(state:AnalysisState) -> dict:
    """Extract file metadata from the user's question"""
    query = state["original_query"]
    files = state.get("files", [])

    queries: Metadata = extract_metadata(query)

    mode = queries.mode

    if mode is None:
        if "neg" or "negative" in files:
            mode = "negative"
        elif "pos" or "positive" in files:
            mode = "positive"
        else:
            mode = None

    return { 
        "group_name":          queries.group_name,
        "paired":              queries.paired,
        "label_is_continuous": queries.label_is_continuous,
        "mode":                mode
    }

def run_analysis_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """
    Call MetaboAnalystR to run the statistical analysis.
    """
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Parameter extraction complete, statistical analysis in progress."})

    files = state.get("files", [])
    if not files:
        return {
            "messages": [AIMessage(content="No CSV file provided. Please upload the peak table.")],
            "analysis_result": {},
        }

    csv_path = files[0]
    group_name = state.get("group_name")

    paired = state.get("paired", False) 
    label_is_continuous = state.get("label_is_continuous", False)

    analysis_result = recommend_and_analysis.invoke({
        "file": csv_path,
        "group_name": group_name,
        "paired": paired,
        "label_is_continuous": label_is_continuous
        })
    
    success = analysis_result.get("success", False)
    
    if success:
        result_files = analysis_result.get("result_files", [])
        msg = f"Analysis complete, results stored in `{result_files}`"
    else:
        error_msg = analysis_result.get("summary") or "Unknown error"
        msg = f"Analysis execution failed:{error_msg}"
    
    result_files = analysis_result.get("result_files", [])
    stat_csv = next((p for p in result_files if "t_test" in p or "anova" in p), "")

    return {
        "messages": [AIMessage(content=msg)],
        "analysis_result": analysis_result,
        "primary_csv_path": stat_csv
    }

def extract_significant_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """Extract significant features and split them into identified / unidentified"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Statistical analysis completed, significant metabolite data extraction in progress."})
    csv_path = state.get("primary_csv_path", "")
    if not csv_path:
        return {"messages": [AIMessage(content="Analysis results CSV not found.")], "significant_metabolites": []}

    try:
        res = extract_significant.invoke({"file": csv_path, "fdr_cutoff": 0.05})
        result_dir = res.get("result_dir", str)
        sig_all = res.get("sig_all", [])
        sig_mz = res.get("sig_mz_features", [])
        sig_names = res.get("sig_identified_metabolites", [])
        all_names = res.get("all_identified_metabolites", [])
        scores = res.get("metabolite_scores", [])
        mumm_txt = res.get("mummichog_txt_path", "")

    except Exception as e:
        return {"messages": [AIMessage(content=f"Extraction failed:{e}")], "significant_metabolites": []}

    msg = (
        f"- Identified metabolites (with names): {len(sig_names)} \n"
        f"- Unidentified mass spectrometry features (pure m/z): {len(sig_mz)} \n"
    )

    if writer:
        writer({"status": f"Significant metabolite data extraction completed (FDR < 0.05), {msg}"})

    return {
        "result_dir" : result_dir,
        "sig_all": sig_all,
        "significant_metabolites": sig_names,   
        "all_detected_features": all_names,       
        "metabolite_scores": scores,               
        "mummichog_peak_table": mumm_txt  
    }

def should_query_pubchem(state: AnalysisState) -> str:
    """
    Based on what extract_significant extracted, decide whether to run
    mummichog or the PubChem lookup plus standard pathway analysis.
    """
    if not state.get("mummichog_peak_table"):
        return "pubchem_lookup"
    return "mummichog_analysis"

def mummichog_analysis_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """mummichog_analysis of the significant metabolites"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Feature extraction complete, mummichog analysis in progress."})
    mumm_csv_path = state.get("mummichog_peak_table", "") 
    mode = state.get("mode", "") 

    if not mumm_csv_path:
        return {"mummichog_result": {}, "messages": [AIMessage(content="Skip Mummichog")]}

    try:
        result = mummichog_analysis.invoke({"peak_table_path": mumm_csv_path, "mode": mode})
        msg = "Mummichog analysis completed"
    except Exception as e:
        result = {"error": str(e)}
        msg = f"Mummichog analysis failed: {str(e)}"
        
    return {
        "mummichog_result": result or {}, 
        "messages": [AIMessage(content=msg)],
    }


def pubchem_lookup_node(state: AnalysisState, config: RunnableConfig) -> dict:
    """Look up PubChem information for the significant metabolites"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Feature extraction complete, PubChem search in progress."})
    metabolites = state.get("significant_metabolites", [])
    if not metabolites:
        return {"pubchem_result": {}, "pubchem_table_text": "No significant information on identified metabolites was found.", "pubchem_kegg_mapping": {}}

    data_list: dict = pubchem_id_mapping.invoke({"metabolite_names": metabolites})
    table_rows = []
    
    # ─── Build a dict holding the extracted fallback KEGG lookup table ───
    pubchem_kegg_mapping = {} 
    
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
        # ─────────────────────────────────────────

        # ─── Pull out the current metabolite's bare KEGG ID as a fallback ───
        kegg_id_list = safe_info.get("kegg", [])
        if isinstance(kegg_id_list, list) and kegg_id_list:
            # Safely get the first non-empty ID (e.g. "C00031")
            first_kegg_id = next((x.get("id") for x in kegg_id_list if x.get("id")), None)
            if first_kegg_id:
                pubchem_kegg_mapping[name] = first_kegg_id
        # ────────────────────────────────────────────────────────

        url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid != 'N/A' else ""
        link = f"[PubChem]({url})" if url else "N/A"
        
        row = f"| {name} | {cid} | {formula} | {weight} | {iupac} | {inch} | {smiles} | {kegg} | {hmdb} | {chebi} | {drugbank} | {link} |"
        table_rows.append(row)

    rows_text = "\n".join(table_rows)
    pubchem_section = f"""
## PubChem Metabolite Details

| name | CID | Molecular Formula | Molecular Weight | IUPAC name | InChIKey | SMILES | KEGG | HMDB | ChEBI | DrugBank | link |
|--------|-----|-----------------|-------------------|-----------|--------|----------|-------|------|------|----------|--------|
{rows_text}
"""
    return {
        "pubchem_result": data_list,
        "pubchem_table_text": pubchem_section,  
        "pubchem_kegg_mapping": pubchem_kegg_mapping,  
        "messages": [AIMessage(content="PubChem metabolite data search complete.")]
    }


def pathway_analysis_node(state: AnalysisState, config: RunnableConfig) -> dict:
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "PubChem search complete, Pathway analysis in progress."})
    """Pathway enrichment analysis of the significant metabolites (ORA + GSEA Prerank)"""
    metabolites = state.get("significant_metabolites", [])
    background_names = state.get("all_detected_features", [])
    scores_list = state.get("metabolite_scores", [])
    pubchem_backup = state.get("pubchem_kegg_mapping")
    workdir = state.get("result_dir")


    if not metabolites:
        return {"pathway_result": {"status": "skipped", "reason": "No significant metabolite input"}}

    try:
        mapping_json = map_names_to_kegg.invoke({"metabolites": metabolites, "pubchem_backup": pubchem_backup})
        df_mapping = pd.read_json(mapping_json)
        sig_ids = []
        if not df_mapping.empty and "kegg_id" in df_mapping.columns:
            sig_ids = df_mapping["kegg_id"].dropna().unique().tolist()
        
        bg_ids = []
        if background_names:
            bg_mapping_json = map_names_to_kegg.invoke({"metabolites": background_names})
            df_bg = pd.read_json(bg_mapping_json)
            if not df_bg.empty and "kegg_id" in df_bg.columns:
                bg_ids = df_bg["kegg_id"].dropna().unique().tolist()
        
        if not bg_ids:
            bg_ids = sig_ids

        ora_result_json = run_ora_analysis.invoke({
            "significant_ids": sig_ids,
            "background_ids": bg_ids,
            "workdir": workdir,
        })
        ora_summary = json.loads(ora_result_json)

        gsea_summary = {"status": "skipped", "reason": "No quantitative score matrix available"}
        if scores_list and not df_mapping.empty:
            name_to_kegg_dict = df_mapping.set_index('name')['kegg_id'].dropna().to_dict()
            mapped_scores_list = []
            for item in scores_list:
                f_name = item.get("feature_name")
                t_score = item.get("t_score")
                k_id = name_to_kegg_dict.get(f_name)
                if k_id:
                    mapped_scores_list.append({"kegg_id": k_id, "t_score": t_score})
            
            if mapped_scores_list:
                scores_json = json.dumps(mapped_scores_list)
                gsea_result_json = run_gsea_prerank.invoke({
                    "metabolite_scores_json": scores_json,
                    "workdir": workdir,
                })
                gsea_summary = json.loads(gsea_result_json)
            else:
                gsea_summary = {"status": "skipped", "reason": "None of the identified metabolites were successfully converted to KEGG ID."}

        final_result = {
            "ora_summary": ora_summary,
            "gsea_summary": gsea_summary,
            "mapped_kegg_ids": sig_ids,
            "report_directory": ["ora_output", "gsea_output"]
        }
        msg = f"Metabolic pathway analysis was successfully completed. The most significant pathway was: {ora_summary.get('top_pathway')}"

    except Exception as e:
        final_result = {"status": "error", "error_message": str(e)}
        msg = f"Pathway analysis failed: {str(e)}"

    return {
        "pathway_result": final_result,
        "messages": [AIMessage(content=msg)],
    }


def save_significant_node(state: dict, config: RunnableConfig) -> dict:
    """Core fix 4: once all parallel analysis nodes have arrived, emit the final combined Markdown report in one place"""
    writer = config.get("configurable", {}).get("writer")
    if writer:
        writer({"status": "Pathway analysis completed, report writing now in progress."})
        
    date            = state.get("date", datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
    # path            = f"research/significant/significant_{date}.md"
    workdir         = state.get("result_dir") or f"uploads/output/analysis/{date}"
    os.makedirs(workdir, exist_ok=True)
    path = os.path.join(workdir, f"significant_{date}.md")
    metabolites     = state.get("sig_all", [])
    files           = state.get("files", [])
    analysis_result = state.get("analysis_result", {})
    r_code          = analysis_result.get("r_code", "")

    # The report is for physicians, so show file names only. `files` may arrive with
    # a prefix like `../../uploads/csv/` -- an internal detail that compensates for the
    # project's three inconsistent BASE_DIRs (see _graph_file_path in api/routers/chat.py);
    # printing it in the report only makes people think it is a bug.
    file_names_text = ", ".join(os.path.basename(str(f)) for f in files) or "N/A"

    # `sig_all = sig_mz_features + sig_identified_metabolites`
    # (extract_significant in use_tool/pathway_analysis.py), so both counts can be
    # derived exactly. They must be stated separately: if the heading only says
    # "Significant Metabolites (Total: 31)" and then lists `327.2/3418`-style entries,
    # physicians will take those unidentified MS features for metabolites. This used to
    # appear only in the status events (the execution trace scrolls away), not in the report.
    identified_metabolites = state.get("significant_metabolites") or []
    identified_count = len(identified_metabolites)
    unidentified_count = max(len(metabolites) - identified_count, 0)
    
    # ── Analysis parameters and rationale ────────────────────────────────
    # `recommend_and_analysis` computes three things: summary / config / recommend,
    # but the report used only r_code and result_files and threw the rest away. After
    # testing it, a user pointed out that "the full report lacks the parameters used...
    # and does not explain why there are no parameters" -- those three are exactly what
    # was missing. Users need to judge whether the result is trustworthy, and they can
    # only question what they can see.
    data_summary = str(analysis_result.get("summary") or "N/A").strip()

    config = analysis_result.get("config") or {}
    # file_path is an internal path (with the compensating ../../ prefix), not an analysis parameter; omit it.
    config_rows = "\n".join(
        f"| `{k}` | `{v}` |" for k, v in config.items() if k != "file_path"
    ) or "| _(none)_ | |"

    recommendations = analysis_result.get("recommend")
    if isinstance(recommendations, list) and recommendations:
        recommend_rows = "\n".join(
            f"| `{r.get('analysis')}` | {r.get('reason', '')} |"
            if isinstance(r, dict) else f"| `{r}` | |"
            for r in recommendations
        )
    else:
        recommend_rows = "| _(no recommendations recorded)_ | |"

    pubchem_table   = state.get("pubchem_table_text", "This analysis did not trigger the identification of metabolites.")
    
    raw_pathway_res = state.get("pathway_result", {})
    pathway_res     = raw_pathway_res.get("pathway_result", raw_pathway_res) if raw_pathway_res else {}
    mummichog_res   = state.get("mummichog_result", {})

    # Collect Mummichog results
    mummichog_summary_text = "* Automatically skip Mummichog predictions (no unidentified features)."
    if mummichog_res and mummichog_res.get("status") != "skipped" and "error" not in mummichog_res:
        mummichog_summary_text = f"* **Mummichog Result**: {mummichog_res.get('result')}"
    elif mummichog_res and "error" in mummichog_res:
        mummichog_summary_text = f"* ⚠️ **Mummichog analysis failed**: {mummichog_res.get('error')}"

    # Collect Pathway results
    pathway_summary_text = "* Automatically skip ORA and GSEA analysis"
    
    if pathway_res and "mapped_kegg_ids" in pathway_res:
        ora_raw = pathway_res.get("ora_summary", {})
        ora = json.loads(ora_raw) if isinstance(ora_raw, str) else ora_raw
        
        gsea_raw = pathway_res.get("gsea_summary", {})
        gsea = json.loads(gsea_raw) if isinstance(gsea_raw, str) else gsea_raw

        top_pathway_name = ora.get("top_pathway_by_p", ora.get("top_pathway", "N/A"))
        top_impact = ora.get("top_pathway_impact", 0.0)
        
        rep_dirs = pathway_res.get("report_directory", [])
        dir_text = ", ".join([f"`{d}`" for d in rep_dirs]) if isinstance(rep_dirs, list) else f"`{rep_dirs}`"

        pathway_summary_text = (
            f"* **Successfully matched KEGG IDs**: {len(pathway_res.get('mapped_kegg_ids', []))} metabolites\n"
            f"* **ORA (with Topology) Summary**:\n"
            f"  - Significantly enriched pathways ($P < 0.05$): {ora.get('significant_pathways_count', 0)}\n"
            f"  - Top perturbed pathway: **{top_pathway_name}** (Pathway Impact Score: {top_impact:.4f})\n"
            f"* **GSEA Summary**:\n"
            f"  - Top enriched term: **{gsea.get('top_enrichment_term', 'N/A')}** (NES: {gsea.get('top_enrichment_nes', 0.0):.4f}, FDR: {gsea.get('top_enrichment_fdr', 1.0):.4f})\n"
            f"* **Output Storage**: Detailed enrichment tables and publication-quality figures are stored in: {dir_text}"
        )
    elif pathway_res and pathway_res.get("status") == "error":
        pathway_summary_text = f"* ⚠️ **Pathway analysis failed**: {pathway_res.get('error_message')}"

    content = f"""# Comprehensive Metabolic Analysis Report

## 📋 Metadata
* **Target File(s)**: {file_names_text}
* **Analysis Start Time**: {date}
* **Filtering Criteria**: FDR < 0.05

---

## 🔬 Data Characteristics
```
{data_summary}
```

---

## ⚙️ Analysis Parameters (Auto-detected / Defaults)

The system set the parameters below from the data characteristics or used the default values. **Normalization and scaling directly affect how the results are interpreted**;
please check that they match your analysis intent.

| Parameter | Value |
| :--- | :--- |
{config_rows}

### Fixed statistical parameters (not adjustable)

The values below are hard-coded in the R script template and **cannot be adjusted** in this version (they are listed so that you can judge whether the results are reliable):

| Parameter | Fixed value | Description |
| :--- | :--- | :--- |
| `fc.thresh` | 2.0 | Fold change significance threshold |
| `threshp` | 0.05 | Adjusted p-value (FDR) threshold |
| `equal.var` | TRUE | Assumes equal variances (Student's t-test); FALSE would give Welch's t-test |
| Multiple-testing correction | `"fdr"` | Benjamini-Hochberg |
| Number of PCA components | 5 | Number of principal components shown in the scree and pairs plots |

---

## 🧭 Why These Analyses

| Module | Reason |
| :--- | :--- |
{recommend_rows}

---

## 💻 Statistical R Script Code
```r
{r_code}
```
---
## Metabolic Physicochemical Data (from PubChem)
{pubchem_table}
---
## List of Significant Features (Total: {len(metabolites)})

* Identified metabolites (with names): {identified_count}
* Unidentified mass-spectrometry features (m/z / retention time only): {unidentified_count}

{chr(10).join(f"- {m}" for m in metabolites) if metabolites else "- No significant features detected."}

1. Functional Prediction (Mummichog)
{mummichog_summary_text}

2. Advanced Pathway Enrichment (ORA & GSEA)
{pathway_summary_text}
"""
    # 1. First write the actual files/folders to disk
    write_file.invoke({"path": path, "content": content})

    # 2. Once the files are confirmed present, notify the frontend to show the download button
    if writer:
        writer({
            "status": "Summary complete! Ready to download.",
            "output_file_path": f"uploads/output/literature/{date}" 
        })

    # 3. Update the backend workflow state
    return {"output_path": path}

# ── Graph assembly ─────────────────────────────────────────────────────────────

def build_analysis_graph():
    builder = StateGraph(AnalysisState)
    
    # Register all nodes
    builder.add_node("extract_metadata",    extract_metadata_node)
    builder.add_node("run_analysis",        run_analysis_node)
    builder.add_node("extract_significant", extract_significant_node)
    builder.add_node("mummichog_analysis",  mummichog_analysis_node)
    builder.add_node("pubchem_lookup",      pubchem_lookup_node)
    builder.add_node("pathway_analysis",    pathway_analysis_node)
    builder.add_node("save_significant",    save_significant_node) 

    # ── 1. Basic linear flow ───────────────────
    builder.add_edge(START,                 "extract_metadata")
    builder.add_edge("extract_metadata",    "run_analysis")
    builder.add_edge("run_analysis",        "extract_significant")
    
    builder.add_conditional_edges(
        "extract_significant",
        should_query_pubchem,
        {
            "pubchem_lookup": "pubchem_lookup", 
            "mummichog_analysis": "mummichog_analysis" 
        }
    )
    builder.add_edge("pubchem_lookup",   "pathway_analysis")

    builder.add_edge("mummichog_analysis",  "save_significant")
    builder.add_edge("pathway_analysis",    "save_significant")
    builder.add_edge("save_significant", END)

    return builder.compile()

analysis_graph = build_analysis_graph()
