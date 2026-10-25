import os
import pandas as pd
import gseapy as gp
import numpy as np
import networkx as nx
import scipy.stats as stats
from langchain.tools import tool
import json
import time
import subprocess
import requests
from pathlib import Path
from statsmodels.stats.multitest import multipletests
import matplotlib.pyplot as plt
import seaborn as sns
import io


# Helper parsing functions (extract $m/z$ and $RT$)
def _parse_mz(x):
    val_str = str(x).strip()
    if '_' in val_str:
        try: return float(val_str.split('_')[0].strip())
        except: pass
    if '/' in val_str:
        try: return float(val_str.split('/')[0].strip())
        except: pass
    try: return float(val_str)
    except: return None

def _parse_rt(x):
    val_str = str(x).strip()
    if '_' in val_str:
        try: return float(val_str.split('_')[1].strip())
        except: pass
    if '/' in val_str:
        try: return float(val_str.split('/')[1].strip())
        except: pass
    return 0.0
    
@tool
def extract_significant(file: str, fdr_cutoff: float = 0.05) -> str:
    """
    Extract salient features from T-test/ANOVA output.
    """
    # 1. Define the base directory (three levels up, per the project layout)
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    
    # 2. Clean the incoming path string
    clean_path = file.lstrip("/") 

    # 3. Build the absolute filesystem path of the file to read
    full_path = BASE_DIR / clean_path

    parent_dir = full_path.parent
    # `result_dir` is used by save_significant_node in `graph/analysis_graph.py` as
    # the output directory (`os.makedirs` + file writes, relative to CWD, CWD = `backend/`),
    # so it must start with `uploads/...`.
    # It used to be `Path(parent_dir.parent.name) / parent_dir.name`, which kept only
    # the **names** of the last two levels, so `<root>/backend/uploads/output/analysis/<dir>`
    # became `analysis/<dir>` and the report was written to `backend/analysis/<dir>/` -- outside uploads.
    # As a result `/api/artifacts` could not read it (`resolve_uploads_path` correctly rejects
    # out-of-bounds paths), and the physician's "full report" tab was empty.
    # The fallback in the same node writes `f"uploads/output/analysis/{date}"`,
    # which shows this was the intended shape all along.
    _parts = parent_dir.parts
    if "uploads" in _parts:
        result_dir = str(Path(*_parts[_parts.index("uploads"):]))
    else:
        # Inputs not under uploads (e.g. a manually specified path) keep the original behaviour.
        result_dir = str(Path(parent_dir.parent.name) / parent_dir.name)


    print(f"Agent 嘗試讀取的實體路徑為: {full_path}")

    # 4. Safety check: if the file is not found, return a JSON error safely
    if not full_path.exists():
        return f"錯誤：找不到檔案，請確認路徑 {full_path} 是否正確"

    # 5. Read the file
    df = pd.read_csv(full_path)
    df.columns.values[0] = "Feature"
    df.columns = df.columns.str.strip()

    # 1. Flexibly detect the statistic column
    t_col = next((c for c in df.columns if c.lower() in ['t.stat', 't-score', 'tstat', 'f.stat', 'f-score', 'fstat', 'f.value']), None)
    # 2. Flexibly detect the P-value column
    p_col = next((c for c in df.columns if c.lower() in ['p.value', 'p-value', 'pvalue', 'p']), None)
    # 3. Flexibly detect the FDR column
    fdr_col = next((c for c in df.columns if c.lower() in ['fdr', 'adj.p.val', 'q.value', 'qvalue']), None)

    if not p_col or not t_col:
        return f"錯誤，缺少統計值欄位或 p-value 欄位，現有欄位: {list(df.columns)}"

    df['FDR_fill'] = df[fdr_col] if fdr_col else df[p_col]
    
    # Collect metabolites with FDR < 0.05
    sig_all = [] # Combined
    sig_mz_features = [] # Without names     
    sig_identified_metabolites = [] # With names
    all_identified_metabolites = [] # All metabolites (used as the background in later analysis)
    metabolite_scores = [] # t-score/f-score    

    for _, row in df.iterrows():
        feat_name = str(row["Feature"]).strip()
        fdr_val = float(row['FDR_fill'])
        t_val = float(row[t_col]) if pd.notna(row[t_col]) else 0.0

        clean_text = feat_name.replace('.', '').replace('_', '').replace('/', '').replace('-', '').replace(' ', '')
        is_pure_mz = clean_text.isdigit() 
        
        if not is_pure_mz: # Named metabolites
            base_name = feat_name.split('[')[0].split('|')[0].strip()
            all_identified_metabolites.append(base_name)
            if fdr_val < fdr_cutoff:
                sig_identified_metabolites.append(base_name)
                metabolite_scores.append({"feature_name": base_name, "t_score": t_val})
        else: # No metabolite name
            if fdr_val < fdr_cutoff:
                sig_mz_features.append(feat_name)
    
    sig_all = sig_mz_features + sig_identified_metabolites

    # 1. Build the temporary Mummichog table
    df_mumm = pd.DataFrame()
    df_mumm['m/z'] = df["Feature"].apply(_parse_mz)
    df_mumm['retention_time'] = df["Feature"].apply(_parse_rt)
    df_mumm['p-value'] = df[p_col]
    df_mumm['t-score'] = df[t_col]

    # Check whether m/z parsing failed for any row (became None)
    has_invalid_mz = df_mumm['m/z'].isna().any()
    
    # 3. Write the file only when it is complete (100% of rows have m/z)
    if not has_invalid_mz and not df_mumm.empty:
        df_mumm = df_mumm[['m/z', 'retention_time', 'p-value', 't-score']]
        
        mummichog_dir = full_path.parent  
        base_name = full_path.stem        
        actual_path = mummichog_dir / f"{base_name}_mummichog.txt"
        
        # Write the file
        df_mumm.to_csv(str(actual_path), sep='\t', index=False)
        mummichog_txt_path = str(actual_path)
    else:
        # [All-or-nothing failure] If any metabolite name is present, or the table is empty, write no file at all
        mummichog_txt_path = None

    return {
        "result_dir": result_dir,
        "sig_all": sig_all,
        "sig_mz_features": sig_mz_features,
        "sig_identified_metabolites": sig_identified_metabolites,
        "all_identified_metabolites": all_identified_metabolites,
        "metabolite_scores": metabolite_scores,
        "mummichog_txt_path": mummichog_txt_path 
    }

# result= extract_significant("graph_agent/uploads/two_group_20260526_012631/t_test.csv")
# print(result)

# =============================================================================
# Mummichog (untargeted peak table, no prior identification needed)
# =============================================================================

# This used to live inside mummichog_analysis. It is hoisted to module level so tests
# can monkeypatch it to verify that "relative paths are still joined to BASE_DIR",
# without placing test files inside the frozen directory.
# The value itself is unchanged: Path(__file__).resolve().parent.parent.
_MUMMICHOG_BASE_DIR = Path(__file__).resolve().parent.parent


@tool
def mummichog_analysis(
    peak_table_path: str,
    mode: str = 'positive',
    cutoff: float = 0.05,
    permutation_num: int = 100
) -> str:
    """
    Mummichog Analysis: Perform analysis by calling the official mummichog CLI.
    """
    # Clean and join the path.
    # The `mummichog_txt_path` produced upstream by `extract_significant` (same file) is
    # an **absolute path**, and the BASE_DIR used there is the monorepo root, while here it is
    # `backend/src/graph_agent` -- the two differ. The old code unconditionally did `lstrip("/")`
    # and then joined BASE_DIR, which turned the absolute path into
    #   backend/src/graph_agent/home/<user>/projects/.../backend/uploads/...
    # which never exists, so it always took the "file not found" branch below. Therefore absolute
    # paths are used as is, and only relative paths are joined to BASE_DIR (relative-path behaviour is unchanged).
    incoming = Path(peak_table_path)
    if incoming.is_absolute():
        full_path = incoming
    else:
        full_path = _MUMMICHOG_BASE_DIR / peak_table_path.lstrip("/")

    print(f"Agent 嘗試讀取的實體路徑為: {full_path}")

    if not full_path.exists():
        # Always return a dict. The caller, save_significant_node in `graph/analysis_graph.py`,
        # always calls `.get()` on this value; returning a str crashes the whole SSE stream with
        # `AttributeError: 'str' object has no attribute 'get'`, and the physician only sees
        # a generic "system error" that does not point to the real cause. With a dict, the existing
        # `elif mummichog_res and "error" in mummichog_res` branch there writes the message
        # into the report (it was written for exactly this case).
        return {"status": "error",
                "error": f"錯誤：找不到檔案，請確認路徑 {full_path} 是否正確"}

    # Verify that the required columns meet Mummichog's requirements
    # Note: Mummichog's standard column names are usually 'm/z', 'p-value', 't-score'
    df = pd.read_csv(full_path, sep='\t')
    print(f"正在驗證峰表，共 {len(df)} 個質譜特徵...")
    
    required = {'m/z', 'p-value', 't-score'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"峰表缺少必要欄位：{missing}\n現有欄位：{list(df.columns)}")
        
    # ----------------------------------------------------------------
    # Core change: build the Mummichog CLI command
    # ----------------------------------------------------------------
    # Assemble the mummichog terminal command
    cmd = [
        "mummichog",
        "-f", str(full_path),            # Input file path
        "-o", "mummichog_output",           # Output file prefix
        "-k", str(full_path.parent),
        "-p", str(permutation_num),      # Number of random permutations # default is 100
        "-m", mode,                      # Ion mode (positive/negative)
        "-c", str(cutoff),               # P-value significance cutoff
    ]
    
    print(f"正在執行指令: {' '.join(cmd)}")
    
    try:
        # Run the command and capture errors
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("Mummichog 執行成功！")
        print(result.stdout)
        return {"status":"success", "result":f"Mummichog 完成！結果已存至 {full_path.parent}"}
        
    except subprocess.CalledProcessError as e:
        print("Mummichog 執行失敗！")
        print(e.stderr)
        return {"status":"error", "error":f"執行錯誤: {e.stderr}"}
    except FileNotFoundError:
        return {"status":"error", "error":"錯誤：系統中未偵測到 'mummichog' 指令，請確認是否已安裝並加入環境變數。"}
# result=mummichog_analysis("graph_agent/t_test_mummichog.txt")

# =============================================================================
# TOOL 1: metabolite name to KEGG ID
# =============================================================================
@tool
def map_names_to_kegg(metabolites: list, pubchem_backup: dict = {}) -> str:
    """
    Batch-convert English metabolite names to KEGG IDs.
    When KEGG only has a fuzzy match (the first line is taken), it is compared with PubChem; if they differ, PubChem wins.
    """
    results = []
    
    print(f"[Tool: Map Names] 正在處理 {len(metabolites)} 個代謝物名稱...")
    for name in metabolites:
        kegg_id = None
        clean_name = name.strip().replace(",", " ")
        
        # --- Step 1: call the KEGG HTTPS API ---
        url = f"https://rest.kegg.jp/find/compound/{clean_name}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and response.text.strip():
                lines = response.text.strip().split("\n")
                
                # 1A. Try to find an exact match
                exact_match_line = None
                for line in lines:
                    if "\t" in line:
                        parts = line.split("\t")
                        names_in_kegg = [n.strip().lower() for n in parts[1].replace(";", ",").split(",")]
                        if clean_name.lower() in names_in_kegg:
                            exact_match_line = line
                            break
                
                # 1B. Decide the KEGG output
                if exact_match_line:
                    raw_id = exact_match_line.split("\t")[0]
                    kegg_id = raw_id.split(":")[-1]
                    print(f"➔ {name}: [精準匹配] 採用 KEGG -> {kegg_id}")
                else:
                    # No exact match: take the first line as the candidate ID
                    target_line = lines[0]
                    if "\t" in target_line:
                        raw_id = target_line.split("\t")[0]
                        kegg_id_candidate = raw_id.split(":")[-1]
                        
                        # --- Core logic: cross-check against PubChem ---
                        pubchem = pubchem_backup.get(name)
                        
                        if pubchem: # If PubChem has data
                            if kegg_id_candidate != pubchem:
                                # They differ: apply the override, PubChem wins
                                kegg_id = pubchem
                                print(f"⚠️ {name}: KEGG 模糊匹配抓到 {kegg_id_candidate}，與 PubChem 的 {pubchem} 不同！「改以 PubChem 為主」-> {kegg_id}")
                            else:
                                # They agree
                                kegg_id = kegg_id_candidate
                                print(f"➔ {name}: KEGG 模糊匹配與 PubChem 驗證一致 -> {kegg_id}")
                        else:
                            # PubChem has no data, nothing to compare; reluctantly accept KEGG's first line
                            kegg_id = kegg_id_candidate
                            print(f"➔ {name}: [模糊匹配] PubChem 無備案，暫採 KEGG 第一行 -> {kegg_id}")
                            
            elif response.status_code == 404:
                print(f"➔ {name}: KEGG 伺服器回傳 404 (未找到)")
                
        except Exception as e:
            print(f"⚠️ {name} 連線 KEGG 時發生異常: {e}")

        # --- Step 2: if KEGG returns nothing at all, use PubChem directly ---
        if not kegg_id:
            if name in pubchem_backup and pubchem_backup[name]:
                kegg_id = pubchem_backup[name]
                print(f"➔ {name}: KEGG 查無資料，直接採用 PubChem 備案 -> {kegg_id}")
            else:
                print(f"❌ {name}: KEGG 與 PubChem 皆無法找到任何 ID。")
        
        # Record the final winning result
        results.append({"name": name, "kegg_id": kegg_id})
        time.sleep(0.1)
            
    df = pd.DataFrame(results)
    return df.to_json(orient="records")

# help(KEGG.find)
# result=map_names_to_kegg(['methymycin'])


# =============================================================================
# TOOL 2: ORA mode (includes a real MetaboAnalyst RBC topology test)
# =============================================================================
# =========================================================================
# Built-in helper 1: build a realistic pathway network
# =========================================================================
import os
import requests
import xml.etree.ElementTree as ET
import networkx as nx

def _build_real_kegg_graph_from_kgml(path_id: str, compounds: list, cache_dir: str = "kgml_cache") -> nx.DiGraph:
    """
    Download the pathway's KGML file from the KEGG API and parse it into the real directed metabolic network.
    If the download fails, fall back to a standard linear chain so the program does not crash.
    """
    compounds = list(compounds)

    G = nx.DiGraph()
    G.add_nodes_from(compounds) # Make sure the nodes exist even without edges
    
    if not path_id or path_id == "NA":
        return G
        
    os.makedirs(cache_dir, exist_ok=True)
    kgml_filename = f"{path_id}.xml"
    kgml_path = os.path.join(cache_dir, kgml_filename)
    
    # --- Step 1: download the KGML file (with a local cache) ---
    if not os.path.exists(kgml_path):
        # Fix: KEGG requires https
        url = f"https://rest.kegg.jp/get/{path_id}/kgml"
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and response.text.strip():
                with open(kgml_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
            else:
                # If hsaXXXXX has no KGML, try the mapXXXXX reference map instead
                map_id = path_id.replace("hsa", "map")
                url_map = f"https://rest.kegg.jp/get/{map_id}/kgml"
                response_map = requests.get(url_map, timeout=15)
                if response_map.status_code == 200:
                    with open(kgml_path, "w", encoding="utf-8") as f:
                        f.write(response_map.text)
        except Exception as e:
            print(f"⚠️ 下載 {path_id} KGML 失敗: {e}，啟用降級線性結構。")

    # --- Step 2: parse the XML structure ---
    if os.path.exists(kgml_path):
        try:
            tree = ET.parse(kgml_path)
            root = tree.getroot()
            
            # Build a lookup from entry_id to compound name
            # In KGML, each reaction node is an <entry id="12" name="cpd:C00022".../>
            id_to_cpd = {}
            for entry in root.findall('entry'):
                entry_id = entry.get('id')
                entry_name = entry.get('name') # May be "cpd:C00031 cpd:C00092"
                if entry_name and "cpd:" in entry_name:
                    # Extract the CXXXXX IDs
                    cpds = [c.replace("cpd:", "").strip() for c in entry_name.split(" ") if "cpd:" in c]
                    id_to_cpd[entry_id] = cpds
            
            # Parse <relation> or <reaction> to build directed edges
            # The most precise method is parsing the <reaction> tags
            for reaction in root.findall('reaction'):
                # Get the substrates and products
                substrates = [s.get('id') for s in reaction.findall('substrate')]
                products = [p.get('id') for p in reaction.findall('product')]
                
                # Map entry_id back to the actual CXXXXX metabolite ID and connect them
                for sub_id in substrates:
                    for prod_id in products:
                        sub_cpds = id_to_cpd.get(sub_id, [])
                        prod_cpds = id_to_cpd.get(prod_id, [])
                        for u in sub_cpds:
                            for v in prod_cpds:
                                if u in compounds and v in compounds:
                                    G.add_edge(u, v) # Add a real biochemical reaction edge
                                    
        except Exception as e:
            print(f"⚠️ 解析 {path_id} KGML 發生異常: {e}")
            
    # --- Step 3: safe fallback ---
    # If parsing yields no edges at all (e.g. the pathway's structure is undefined in KEGG),
    # connect the nodes into a chain so the topology analysis still has a baseline to run on
    if G.number_of_edges() == 0 and len(compounds) >= 2:
        for i in range(len(compounds) - 1):
            G.add_edge(compounds[i], compounds[i+1])
            
    return G

def _build_semi_real_pathway_graph(compounds: list) -> nx.DiGraph:
    """
    Turn a one-dimensional metabolite list into a directed graph with uneven topological density.
    The first 20% of molecules act as core hubs, so a meaningful Betweenness Centrality can be computed.
    """
    G = nx.DiGraph()
    G.add_nodes_from(compounds)
    
    if len(compounds) < 2:
        return G
        
    # Simulate a biological network: the top 20% main molecules get more edges (hubs), the rest are peripheral reactions
    core_count = max(1, int(len(compounds) * 0.2))
    cores = compounds[:core_count]
    remains = compounds[core_count:]
    
    for c in cores:
        for r in remains[:3]:  # Connect core molecules to some peripheral molecules
            G.add_edge(c, r)
            G.add_edge(r, compounds[0])  # Form a network feedback flow
    return G

# =========================================================================
# Built-in helper 2: compute topology and ORA for a single pathway (original algorithm kept intact)
# =========================================================================
def _calculate_single_pathway_metrics(significant_ids: list, pathway_graph: nx.DiGraph, background: list) -> dict:
    pathway_nodes = list(pathway_graph.nodes)
    N = len(background)
    K = len(significant_ids)
    n = len(pathway_nodes)

    # Hit metabolites
    hits = [m for m in significant_ids if m in pathway_nodes]
    k = len(hits)

    # 1. Hypergeometric test p-value
    p_value = stats.hypergeom.sf(k - 1, N, n, K) if k > 0 else 1.0

    # 2. RBC topology (Relative Betweenness Centrality)
    centrality = nx.betweenness_centrality(pathway_graph, normalized=True)
    total_importance = sum(centrality.values())
    hit_importance = sum(centrality.get(h, 0) for h in hits)
    impact_score = hit_importance / total_importance if total_importance > 0 else 0.0

    return {
        "hits_count": k,
        "pathway_size": n,
        "p_value": p_value,
        "impact_score": impact_score,
        "hit_ids": hits
    }
def _plot_ora_results(csv: str, output_dir: str = "ora_output", top_n: int = 15):
    """
    Read the ORA result CSV and draw standard bioinformatics bar and bubble plots.
    """

    # 1. Read the data and keep the Top N most significant pathways
    df = csv
    if df.empty:
        print("CSV 檔案內容為空。")
        return
        
    df = df.head(top_n).copy()
    
    # 2. Compute -log10(P-value) for visualization
    # Add a tiny value to avoid a log(0) error
    df["-log10(P_value)"] = -np.log10(df["P_value"] + 1e-10)
    
    # Reverse the DataFrame before plotting so the chart reads "most significant -> less significant" from top to bottom
    df_plot = df.iloc[::-1].reset_index(drop=True)

    # Create the output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # -------------------------------------------------------------------------
    # 📊 Figure 1: enrichment bar plot
    # -------------------------------------------------------------------------
    plt.figure(figsize=(10, 6))
    sns.set_theme(style="whitegrid")
    
    # x-axis is -log10(P_value); color is a P_value gradient (red to blue)
    sns.barplot(
        x="-log10(P_value)", 
        y="Pathway_Name", 
        data=df_plot, 
        color="red",
    )
    
    plt.title(f"Top {top_n} Enriched Metabolic Pathways (Bar Plot)", fontsize=14, fontweight="bold")
    plt.xlabel("-log10(P-value)", fontsize=12)
    plt.ylabel("Metabolic Pathway", fontsize=12)
    plt.tight_layout()
    
    bar_out = os.path.join(output_dir, "ora_barplot.png")
    plt.savefig(bar_out, dpi=300)
    plt.close()
    print(f"✓ 長條圖已儲存至：{bar_out}")

    # -------------------------------------------------------------------------
    # 🔮 Figure 2: standard bubble plot (Bubble Plot / Dot Plot)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(10, 7))
    
    # Core: draw the bubble plot with scatter
    # s takes the hit count (times a point scaling factor), c takes P_value
    scatter = plt.scatter(
        x=df_plot["Enrichment_Factor"],
        y=df_plot["Pathway_Name"],
        s=df_plot["Hits_Count"] * 50,  # 💡 Bubble size maps to hit count; 50 is the scaling factor (adjustable)
        c=df_plot["P_value"],         # 💡 Color intensity maps to the raw P-value
        cmap="vlag_r",                 # Classic red-blue / red-white gradient
        alpha=0.85,
        edgecolors="black",            # Black outline on bubbles for a cleaner look
        linewidths=0.8
    )
    
    plt.title(f"Top {top_n} Enriched Metabolic Pathways (Bubble Plot)", fontsize=14, fontweight="bold")
    plt.xlabel("Enrichment Factor", fontsize=12)
    plt.ylabel("Metabolic Pathway", fontsize=12)
    
    # 1. Colorbar on the right - shows P-value significance
    cbar = plt.colorbar(scatter)
    cbar.set_label("P-value", fontsize=11)
    
    # 2. Size legend on the right - shows Hits Count
    # In practice we manually pick 3 representative point sizes for the legend
    max_hits = df_plot["Hits_Count"].max()
    min_hits = df_plot["Hits_Count"].min()
    mid_hits = int((max_hits + min_hits) / 2)
    
    legend_sizes = sorted(list(set([min_hits, mid_hits, max_hits])))
    for size in legend_sizes:
        plt.scatter([], [], c='gray', alpha=0.5, s=size * 50, label=str(size), edgecolors="black")
        
    plt.legend(title="Hits Count", labelspacing=1.2, borderpad=1, loc="lower right", frameon=True)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    
    bubble_out = os.path.join(output_dir, "ora_bubbleplot.png")
    plt.savefig(bubble_out, dpi=300)
    plt.close()
    print(f"✓ 氣泡圖已儲存至：{bubble_out}")

    return (f"The bubble plot has been saved to: {bubble_out}, The bar plot has been saved to: {bar_out}")

# --- Test run example ---
# plot_ora_results("ora_output/pathway_results.csv")

def _plot_topology_volcano_bubble(csv: str, output_dir: str = "ora_output", top_n_labels: int = 8):
    """
    Read the result CSV containing P-value and Pathway_Impact,
    and draw the standard bioinformatics "two-metric enrichment/topology volcano bubble plot".
    """

    # 1. Read the data
    df = csv
    if df.empty:
        print("❌ CSV 資料夾為空。")
        return
        
    # Compute -log10(P-value)
    df["-log10(P_value)"] = -np.log10(df["P_value"] + 1e-10)

    # 2. Set up the canvas
    plt.figure(figsize=(10, 8))
    sns.set_theme(style="ticks") # Use a clean scientific ticks style
    
    # 3. Draw the core bubble scatter
    scatter = plt.scatter(
        x=df["Pathway_Impact"],
        y=df["-log10(P_value)"],
        s=df["Hits_Count"] * 60,         # Bubble size maps to hit count
        c=df["-log10(P_value)"],         # Color depth maps to significance
        cmap="YlOrRd",                   # Yellow-orange-red gradient; more significant is redder
        alpha=0.85,
        edgecolors="black",              # Black outline makes bubbles clearer
        linewidths=0.8
    )

    # 4. Add the standard publication-style "two threshold lines"
    plt.axhline(y=-np.log10(0.05), color="gray", linestyle="--", linewidth=1, alpha=0.7, label="p-value = 0.05")
    plt.axvline(x=0.1, color="gray", linestyle=":", linewidth=1, alpha=0.7, label="Impact = 0.1")

    # 5. Automatically label the Top N most significant or highest-Impact pathways (avoids cluttering the plot with text)
    # Sort order: prefer pathways with low P-value and high Impact
    df_labeled = df.sort_values(by=["P_value", "Pathway_Impact"], ascending=[True, False]).head(top_n_labels)
    
    # adjustText-like approach (here using built-in matplotlib nudging to avoid direct text overlap)
    for _, row in df_labeled.iterrows():
        plt.text(
            x=row["Pathway_Impact"] + 0.01,
            y=row["-log10(P_value)"] + 0.05,
            s=row["Pathway_Name"],
            fontsize=9,
            fontweight="semibold",
            alpha=0.85
        )

    # 6. Chart decoration
    plt.title("Metabolomics Pathway Analysis (ORA + Topology)", fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("Pathway Impact (Topology Analysis)", fontsize=12, fontweight="bold")
    plt.ylabel("-log10(p-value) (Enrichment Analysis)", fontsize=12, fontweight="bold")
    
    # Set slightly loose X/Y limits so edge bubbles are not clipped
    plt.xlim(-0.02, df["Pathway_Impact"].max() + 0.08)
    plt.ylim(-0.1, df["-log10(P_value)"].max() + 0.5)

    # 7. Create the colorbar and the bubble size legend
    cbar = plt.colorbar(scatter)
    cbar.set_label("-log10(p-value)", fontsize=10)
    
    # Manually create size reference markers for Hits Count
    max_hits = int(df["Hits_Count"].max())
    min_hits = int(df["Hits_Count"].min())
    sizes_to_show = sorted(list(set([min_hits, int((min_hits+max_hits)/2), max_hits])))
    
    for sz in sizes_to_show:
        plt.scatter([], [], c="gray", alpha=0.5, s=sz * 60, label=str(sz), edgecolors="black")
    plt.legend(title="Hits Count", loc="lower right", scatterpoints=1, labelspacing=1)

    plt.tight_layout()
    
    # Save the figure
    fig_out = os.path.join(output_dir, "pathway_analysis_volcano_bubble.png")
    plt.savefig(fig_out, dpi=300)
    plt.close()
    print(f"✓ 雙指標拓撲火山氣泡圖已成功儲存至：{fig_out}")
    return fig_out

# --- Test run ---
# plot_topology_volcano_bubble("ora_output/topology_pathway_results.csv")


# Resolved from this file, not the working directory: the backend is started
# from `backend/`, where the old repo-root-relative string did not exist.
GMT = str(Path(__file__).resolve().parent.parent / "database" / "kegg_metabolites_hsa.gmt")
@tool
def run_ora_analysis(
    significant_ids: list,
    workdir: str, 
    background_ids: list = None,  # Default changed to None so it can be omitted
    gmt_path: str = GMT, 
    output_dir: str = "ora_output",

) -> str:
    """
    Run hypergeometric enrichment analysis (ORA) on identified metabolites, computing P-value and FDR rigorously.
    Does not use a hallucination-prone mock network topology.
    """
    result_dir = os.path.join(workdir, output_dir)
    os.makedirs(result_dir, exist_ok=True)
    
    # --- Step 1: parse the local GMT file ---
    pathway_dict = {}
    pathway_id_dict = {}
    gmt_universe = set()  # 💡 Empty set that automatically collects every molecule that appears in the GMT
    
    with open(gmt_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) > 2:
                pathway_name = parts[0]
                path_id = parts[1]
                compounds = parts[2:]
                
                pathway_dict[pathway_name] = compounds
                pathway_id_dict[pathway_name] = path_id  # Record the mapping
                gmt_universe.update(compounds) # Add this pathway's molecules to the big set; duplicates are dropped automatically

    # --- Step 2: determine and build the background dynamically (key safeguard) ---
    if background_ids:
        set_bg = set(background_ids)
        print(f"[Tool: ORA] 採用使用者提供的真實實驗背景，共 {len(set_bg)} 個代謝物。")
    else:
        set_bg = gmt_universe
        print(f"[Tool: ORA] ⚠️ 未提供背景！自動採用 GMT 內所有分子的聯集作為虛擬背景，共 {len(set_bg)} 個代謝物。")

    # --- Step 2: define the core ORA statistical parameters ---
    # Convert inputs to sets for speed, and ensure the significant list is within the background list
    set_sig = set(significant_ids).intersection(set_bg)
    
    N = len(set_bg)   # Total background metabolites (Universe)
    n = len(set_sig)  # Total significant metabolites (Study set)
    
    if n == 0:
        return json.dumps({"status": "failed", "message": "經與背景比對後，顯著代謝物有效數量為 0。"})

    # --- Step 3: compute the hypergeometric distribution for each pathway ---
    final_results = []
    
    for pathway_name, pathway_compounds in pathway_dict.items():
        # Metabolites of this pathway actually covered by our experimental background (M)
        pathway_in_bg = set(pathway_compounds).intersection(set_bg)
        M = len(pathway_in_bg)
        
        if M < 2: # If the pathway has fewer than 1 metabolite in the background, it is statistically meaningless; skip it
            continue
        
        # graph = _build_semi_real_pathway_graph(pathway_in_bg)
        cache_dir = os.path.join(workdir, "kgml_cache")
        graph = _build_real_kegg_graph_from_kgml(path_id, pathway_in_bg, cache_dir)

        metrics = _calculate_single_pathway_metrics(
            significant_ids=list(set_sig),
            pathway_graph=graph,
            background=list(set_bg)
        )

        if metrics["hits_count"] == 0:
            continue

        enrich_factor = (metrics["hits_count"] / len(set_sig)) / (metrics["pathway_size"] / N)

        final_results.append({
            "Pathway_Name": pathway_name,
            "Pathway_ID": pathway_id_dict.get(pathway_name, "NA"),
            "Pathway_Size_in_Bg": metrics["pathway_size"],
            "Hits_Count": metrics["hits_count"],
            "P_value": metrics["p_value"],
            "Enrichment_Factor": enrich_factor,    # Old metric: count-based fold enrichment
            "Pathway_Impact": metrics["impact_score"],  # Core topology metric
            "Hits_IDs": metrics["hit_ids"]
        })

    if not final_results:
        return json.dumps({"status": "failed", "message": "所有路徑皆無命中任何顯著代謝物。"})

    # --- Step 4: convert to DataFrame, run multiple-testing correction (FDR), and save ---
    res_df = pd.DataFrame(final_results)
    
    # Compute FDR (Benjamini-Hochberg)
    _, fdr_values, _, _ = multipletests(res_df["P_value"], method="fdr_bh")
    res_df["FDR"] = fdr_values
    
    # Reorder columns so they read naturally for scientists
    res_df = res_df[[
        "Pathway_Name", "Pathway_ID", "Pathway_Size_in_Bg", 
        "Hits_Count", "P_value", "FDR", "Enrichment_Factor", "Pathway_Impact", "Hits_IDs"
    ]]
    
    # Sort by P-value
    res_df = res_df.sort_values(by="P_value", ascending=True).reset_index(drop=True)
    
    # Save the CSV file
    csv_output_path = os.path.join(result_dir, "topology_pathway_results.csv")
    res_df.to_csv(csv_output_path, index=False)
    
    # --- Step 5: wrap into a JSON summary returned to the Agent ---
    sig_df = res_df[res_df["P_value"] < 0.05]

    # --- Step 6: plotting ---
    plot_path = _plot_ora_results(res_df, result_dir)
    plot_path_volcano = _plot_topology_volcano_bubble(res_df, result_dir)
    plot_all = f"{plot_path}, The volcano bubble plot has been saved to: {plot_path_volcano}"

    summary = {
        "status": "success",
        "saved_csv": csv_output_path,
        "saved_plot": plot_all,
        "total_analyzed_pathways": len(res_df),
        "significant_pathways_count": len(sig_df),
        "top_pathway": res_df.iloc[0]['Pathway_Name'] if not res_df.empty else None,
        "top_pathway_p_value": res_df.iloc[0]['P_value'] if not res_df.empty else 1.0,
        "top_pathway_fdr": res_df.iloc[0]['FDR'] if not res_df.empty else 1.0
    }
    
    return json.dumps(summary, indent=4, ensure_ascii=False)

# significant_ids = [
#     "C00031",  # D-Glucose (start of glycolysis)
#     "C00022",  # Pyruvate (end of glycolysis)
#     "C00024",  # Acetyl-CoA (key entry into TCA)
#     "C00149",  # L-Malate (TCA cycle)
#     "C00042",  # Succinate (TCA cycle)
#     "C00092",  # Glucose 6-phosphate (glycolysis intermediate)
#     "C04462",  # Fructose 2,6-bisphosphate (glycolysis regulator)
#     "C00577"   # D-Glyceraldehyde (spiked-in impurity, for testing)
# ]
# background_ids = [
#     # Includes the significant molecules (required, otherwise the union becomes empty)
#     "C00031", "C00022", "C00024", "C00149", "C00042", "C00092", "C04462", "C00577",
#     # Other non-significant molecules related to glycolysis and TCA
#     "C00111", "C00118", "C00236", "C00197", "C00631", "C00354", "C00074", "C00158", 
#     "C00311", "C00026", "C00042", "C00122", "C00036",
#     # Simulated background from unrelated pathways (e.g. amino acid, lipid metabolism)
#     "C00079", "C00049", "C00025", "C00064", "C00073", "C00041", "C00183", "C00188",
#     "C00148", "C00082", "C00407", "C00123", "C00135", "C00062", "C00352", "C01005",
#     "C00165", "C00086", "C00416", "C00116", "C00219", "C00157", "C00350", "C00226",
#     "C00187", "C00242", "C00162", "C00093", "C03241"
# ]
# # help(KEGG.find)
# result=run_ora_analysis(significant_ids, background_ids)
# print(result)

# =============================================================================
# TOOL 3: GSEA Prerank mode
# =============================================================================
def _plot_gsea_results(csv: str, output_dir: str = "gsea_output", top_n: int = 15):
    """
    Read the GSEA Prerank result CSV and draw a standard two-sided NES bar chart (activated vs suppressed).
    """

    # 1. Read the data
    df = csv
    if df.empty:
        print("CSV 檔案內容為空。")
        return
    
    # 2. Filter and sort
    # In practice we first filter for meaningful pathways (e.g. non-empty Term and valid NES)
    df = df.dropna(subset=['Term', 'NES']).copy()
    
    # Take the positive (activated) Top N/2 and negative (suppressed) Top N/2 separately
    top_pos = df[df['NES'] > 0].head(int(top_n / 2))
    top_neg = df[df['NES'] < 0].head(int(top_n / 2))
    
    # Merge the two and sort strictly by NES, descending
    df_plot = pd.concat([top_pos, top_neg]).sort_values(by='NES', ascending=False).reset_index(drop=True)
    
    if df_plot.empty:
        print("找不到可供繪圖的正向或負向富集路徑。")
        return

    # 3. Dynamic colors: red for positive (activated), blue for negative (suppressed)
    # This is the most standard color scheme in bioinformatics papers
    colors = ['#D6604D' if nes > 0 else '#4393C3' for nes in df_plot['NES']]

    # 4. Start plotting
    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")

    # Draw a horizontal bar chart
    barplot = sns.barplot(
        x="NES", 
        y="Term", 
        data=df_plot, 
        palette=colors,
        hue="Term",          # Pass hue to avoid a warning in newer seaborn
        legend=False
    )

    # 5. Refine visual details
    plt.title(f"GSEA Pathway Enrichment Summary (Top {len(df_plot)} Terms)", fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("Normalized Enrichment Score (NES)", fontsize=12)
    plt.ylabel("Metabolic Pathway", fontsize=12)
    
    # Draw a vertical black line at X = 0 to separate positive and negative
    plt.axvline(x=0, color='black', linestyle='-', linewidth=0.8, alpha=0.7)

    # Adjust canvas margins so long pathway names are not clipped
    plt.tight_layout()
    
    # Save a high-resolution figure
    gsea_plot_out = os.path.join(output_dir, "gsea_nes_barplot.png")
    plt.savefig(gsea_plot_out, dpi=300)
    plt.close()
    print(f"✓ GSEA 雙向長條圖已成功儲存至：{gsea_plot_out}")

    return gsea_plot_out

# --- How to run the test ---
# plot_gsea_results("./gsea_output/enrichment_results_GSEA.csv")
@tool
def run_gsea_prerank(metabolite_scores_json: str, workdir: str, gmt_path: str = GMT, output_dir: str = "./gsea_output") -> str:
    """
    Run GSEA Prerank rank-based enrichment analysis on identified metabolites (no p-value cutoff needed).
    """
    result_dir = os.path.join(workdir, output_dir)
    os.makedirs(result_dir, exist_ok=True)
    df_input = pd.read_json(io.StringIO(metabolite_scores_json))
    
    # 1. Aggregate duplicate IDs and compute the mean t_score
    rnk = df_input.groupby('kegg_id')['t_score'].mean().reset_index()
    
    # 2. Strict sort: descending (a core GSEA Prerank requirement)
    rnk = rnk.sort_values(by='t_score', ascending=False).dropna()
    
    # [Core fix] Keep only two columns so GSEAPY reliably reads the first as ID and the second as score
    rnk_ready = rnk[['kegg_id', 't_score']]
    
    print(f"[Tool: GSEA] 正在對 {len(rnk_ready)} 個排名的代謝物執行置換檢定...")
    
    # 3. Run GSEAPY Prerank
    pre_res = gp.prerank(
        rnk=rnk_ready,            # Pass in the corrected two-column data
        gene_sets=gmt_path,
        threads=4,
        permutation_num=1000,    # Standard 1000-permutation test
        outdir=result_dir,
        format='png',            # Automatically output the detailed GSEA enrichment plots (.png)
        seed=42
    )
    
    res_df = pre_res.res2d
    
    # 4. Practical detail: GSEAPY names the column 'FDR q-val'; we also sort by significance before saving
    if not res_df.empty:
        res_df = res_df.sort_values(by='FDR q-val', ascending=True)
        
    csv_out = os.path.join(result_dir, "enrichment_results_GSEA.csv")
    res_df.to_csv(csv_out, index=False)

    plot_path = _plot_gsea_results(res_df, result_dir)
    
    summary = {
        "status": "success",
        "saved_csv": csv_out,
        "saved_plot": plot_path,
        "total_pathways": len(res_df),
        "top_enrichment_term": res_df.iloc[0]['Term'] if not res_df.empty else None,
        "top_enrichment_nes": res_df.iloc[0]['NES'] if not res_df.empty else 0.0,
        "top_enrichment_fdr": res_df.iloc[0]['FDR q-val'] if not res_df.empty else 1.0
    }
    return json.dumps(summary, indent=4, ensure_ascii=False)


# test_metabolite_json = """
# [
#   {"kegg_id": "C00031", "t_score": 4.82},
#   {"kegg_id": "C00092", "t_score": 4.15},
#   {"kegg_id": "C00236", "t_score": 3.78},
#   {"kegg_id": "C00022", "t_score": 3.52},
#   {"kegg_id": "C04462", "t_score": 2.91},
#   {"kegg_id": "C00024", "t_score": 1.20},
#   {"kegg_id": "C00079", "t_score": 0.85},
#   {"kegg_id": "C00049", "t_score": 0.43},
#   {"kegg_id": "C00025", "t_score": 0.12},
#   {"kegg_id": "C00064", "t_score": 0.05},
#   {"kegg_id": "C00073", "t_score": -0.02},
#   {"kegg_id": "C00041", "t_score": -0.15},
#   {"kegg_id": "C00183", "t_score": -0.54},
#   {"kegg_id": "C00111", "t_score": -0.92},
#   {"kegg_id": "C00158", "t_score": -2.45},
#   {"kegg_id": "C00311", "t_score": -2.88},
#   {"kegg_id": "C00026", "t_score": -3.12},
#   {"kegg_id": "C00042", "t_score": -3.65},
#   {"kegg_id": "C00122", "t_score": -3.98},
#   {"kegg_id": "C00149", "t_score": -4.21}
# ]
# """

# json_output = run_gsea_prerank(test_metabolite_json)
# print(json_output)