
import urllib.request
import zipfile
import os
import re
import time
import requests
import pandas as pd

def download_smpdb_metabolite_gmt(output_gmt_path="smpdb_metabolites.gmt"):
    """
    Download the SMPDB database, parse it, and save it as a GMT file on disk.
    Unified format: pathway name \t SMPDB_ID \t CXXXXX ...
    """
    url = "https://smpdb.ca/downloads/smpdb_metabolites.csv.zip"
    zip_path = "smpdb_metabolites.zip"
    
    if not os.path.exists(zip_path):
        print("從 SMPDB 下載原始資料壓縮包...")
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, zip_path)
        
    all_dfs = []
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        file_list = zip_ref.namelist()
        target_files = [f for f in file_list if "smpdb_metabolites" in f and f.endswith('.csv')]
        if not target_files:
            target_files = [f for f in file_list if f.endswith('.csv')]
            
        print(f"開始解析 {len(target_files)} 個 SMPDB CSV 檔案...")
        for csv_name in target_files:
            try:
                with zip_ref.open(csv_name) as f:
                    temp_df = pd.read_csv(f, sep=None, engine='python')
                    if not temp_df.empty:
                        temp_df.columns = temp_df.columns.str.strip().str.replace('.', ' ', regex=False)
                        all_dfs.append(temp_df)
            except Exception as e:
                print(f" 跳過檔案 {csv_name}: {e}")

    if not all_dfs:
        print("失敗：沒有讀取到任何 SMPDB 資料。")
        return
        
    df = pd.concat(all_dfs, ignore_index=True)
    
    kegg_col = 'KEGG ID'
    pathway_col = 'Pathway Name'
    smpdb_id_col = 'SMPDB ID'
    
    # Make sure empty values are removed
    df = df[df[kegg_col].notna() & (df[kegg_col].astype(str).str.strip() != "")]
    
    grouped = df.groupby(pathway_col)
    
    with open(output_gmt_path, "w", encoding="utf-8") as gmt_file:
        for path_name, group in grouped:
            smpdb_id = group[smpdb_id_col].iloc[0] if smpdb_id_col in group.columns else "NA"
            compounds = list(set(group[kegg_col].astype(str).str.strip()))
            
            # Filter out entries that are not standard KEGG IDs
            compounds = [c for c in compounds if c.startswith("C") and len(c) == 6]
            
            if compounds:
                # Unified format: pathway name as the first column
                gmt_file.write(f"{path_name}\t{smpdb_id}\t" + "\t".join(compounds) + "\n")
                
    print(f"SMPDB 資料庫已成功儲存至：{output_gmt_path}")


# KEGG answers HTTP 403 once a client goes faster than it allows (measured
# 2026-10-25: at 0.1 s spacing, request 22 onward got 403). Pace requests and
# retry refusals with backoff instead of skipping the pathway.
KEGG_REQUEST_INTERVAL_SEC = 0.4
KEGG_RETRY_DELAYS_SEC = (2, 5, 10, 20, 40)


def _kegg_get(url: str, headers: dict) -> requests.Response:
    """GET a KEGG REST URL, retrying 403/429/5xx and connection errors.

    Returns the first 200 or 404 response (404 is a real answer: the pathway
    has no organism-specific entry). Raises RuntimeError when every attempt
    is refused, so the caller can never mistake a refusal for an empty pathway.
    """
    last_error = ""
    for delay in (0, *KEGG_RETRY_DELAYS_SEC):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            last_error = repr(e)
            continue
        if resp.status_code in (200, 404):
            return resp
        last_error = f"HTTP {resp.status_code}"
    raise RuntimeError(f"KEGG request failed after retries: {url} ({last_error})")


def download_kegg_metabolite_gmt(output_gmt_path: str = "kegg_metabolites_hsa.gmt", organism: str = "hsa"):
    """
    Download all metabolic pathways and Compound IDs from the KEGG REST API and save them in GMT format.
    Unified format: pathway name \t Pathway_ID \t CXXXXX ...

    The file is written to a temporary path and moved into place only when
    every pathway was fetched. If any pathway still fails after retries, this
    raises RuntimeError and leaves no output file, because a truncated GMT
    changes enrichment results without any visible error.
    """
    BASE_URL = "https://rest.kegg.jp"
    headers  = {"User-Agent": "Mozilla/5.0"}

    print(f"Step 1: 取得 {organism} pathway 清單...")
    resp = _kegg_get(f"{BASE_URL}/list/pathway/{organism}", headers)
    if resp.status_code != 200:
        raise RuntimeError(f"KEGG pathway list unavailable for {organism}: HTTP {resp.status_code}")

    pathways = {}
    for line in resp.text.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        path_id   = parts[0].replace("path:", "")        # e.g., hsa00010
        path_name = parts[1].split(" - ")[0].strip()     # e.g., Glycolysis / Gluconeogenesis
        pathways[path_id] = path_name

    if not pathways:
        raise RuntimeError(f"KEGG returned no pathways for {organism}")

    print(f"  ✓ 找到 {len(pathways)} 條 pathway\n")
    print("Step 2: 下載各 pathway 的 Compound ID...")

    success_count = 0
    empty_count   = 0
    failed_ids    = []
    tmp_path = f"{output_gmt_path}.partial"

    try:
        with open(tmp_path, "w", encoding="utf-8") as gmt_file:
            for idx, (path_id, path_name) in enumerate(pathways.items(), 1):
                time.sleep(KEGG_REQUEST_INTERVAL_SEC)
                try:
                    # [Connection optimisation] Query the organism pathway directly (e.g. hsa00010); fall back to map only if nothing is found
                    link_resp = _kegg_get(f"{BASE_URL}/link/compound/{path_id}", headers)

                    # If hsa is not found, switch to the map fallback automatically
                    if link_resp.status_code == 404 or not link_resp.text.strip():
                        map_id = re.sub(f"^{organism}", "map", path_id)
                        time.sleep(KEGG_REQUEST_INTERVAL_SEC)
                        link_resp = _kegg_get(f"{BASE_URL}/link/compound/{map_id}", headers)
                except RuntimeError as e:
                    failed_ids.append(path_id)
                    print(f"  ✗ {path_id} 失敗: {e}")
                    continue

                compounds = []
                raw_text  = link_resp.text.strip() if link_resp.status_code == 200 else ""

                if raw_text:
                    for line in raw_text.split("\n"):
                        parts = line.split("\t")
                        if len(parts) == 2:
                            cpd_id = parts[1].replace("cpd:", "").strip()
                            if cpd_id.startswith("C") and len(cpd_id) == 6:   # Keep only standard C numbers (e.g. C00031)
                                compounds.append(cpd_id)

                if compounds:
                    # [Core fix]: use path_name as the first column, consistent with SMPDB's behaviour!
                    # Format: pathway name \t pathway ID \t metabolite1 \t metabolite2 ...
                    gmt_file.write(f"{path_name}\t{path_id}\t" + "\t".join(compounds) + "\n")
                    success_count += 1
                else:
                    empty_count += 1

                if idx % 20 == 0:
                    print(f"  進度: {idx:3d} / {len(pathways)} | 成功: {success_count} | 空白: {empty_count} | 失敗: {len(failed_ids)}")

        if failed_ids:
            raise RuntimeError(
                f"{len(failed_ids)} KEGG pathways could not be fetched; no GMT was written: "
                + ", ".join(failed_ids)
            )
        os.replace(tmp_path, output_gmt_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    print(f"\n✓ 完成！GMT 資料庫已儲存至：{output_gmt_path} (成功: {success_count}, 空白: {empty_count})")
import os
import requests
import xml.etree.ElementTree as ET
import networkx as nx

def _build_real_kegg_graph_from_kgml(path_id: str, compounds: list, cache_dir: str = "kgml_cache") -> nx.DiGraph:
    """
    Automatically download the pathway's KGML file from the KEGG API and parse it into the real directed metabolic network graph.
    If the download fails, fall back to standard linear edges so the program does not crash.
    """
    G = nx.DiGraph()
    G.add_nodes_from(compounds) # Make sure the nodes exist even without a connection
    
    if not path_id or path_id == "NA":
        return G
        
    os.makedirs(cache_dir, exist_ok=True)
    kgml_filename = f"{path_id}.xml"
    kgml_path = os.path.join(cache_dir, kgml_filename)
    
    # ─── Step 1: download the KGML file (with local cache) ───
    if not os.path.exists(kgml_path):
        # Fix: KEGG requires https
        url = f"https://rest.kegg.jp/get/{path_id}/kgml"
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and response.text.strip():
                with open(kgml_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
            else:
                # If no KGML exists for hsaXXXXX, try the mapXXXXX reference map instead
                map_id = path_id.replace("hsa", "map")
                url_map = f"https://rest.kegg.jp/get/{map_id}/kgml"
                response_map = requests.get(url_map, timeout=15)
                if response_map.status_code == 200:
                    with open(kgml_path, "w", encoding="utf-8") as f:
                        f.write(response_map.text)
        except Exception as e:
            print(f"下載 {path_id} KGML 失敗: {e}，啟用降級線性結構。")

    # ─── Step 2: parse the XML structure ───
    if os.path.exists(kgml_path):
        try:
            tree = ET.parse(kgml_path)
            root = tree.getroot()
            
            # Build a mapping from entry_id to compound name
            # In KGML, each reaction node is an <entry id="12" name="cpd:C00022".../>
            id_to_cpd = {}
            for entry in root.findall('entry'):
                entry_id = entry.get('id')
                entry_name = entry.get('name') # May be "cpd:C00031 cpd:C00092"
                if entry_name and "cpd:" in entry_name:
                    # Extract the CXXXXX number
                    cpds = [c.replace("cpd:", "").strip() for c in entry_name.split(" ") if "cpd:" in c]
                    id_to_cpd[entry_id] = cpds
            
            # Parse <relation> or <reaction> to build arrow edges
            # The most accurate approach is to parse <reaction> tags
            for reaction in root.findall('reaction'):
                # Get the substrates and products
                substrates = [s.get('id') for s in reaction.findall('substrate')]
                products = [p.get('id') for p in reaction.findall('product')]
                
                # Map entry_id back to the actual CXXXXX metabolite ID and connect
                for sub_id in substrates:
                    for prod_id in products:
                        sub_cpds = id_to_cpd.get(sub_id, [])
                        prod_cpds = id_to_cpd.get(prod_id, [])
                        for u in sub_cpds:
                            for v in prod_cpds:
                                if u in compounds and v in compounds:
                                    G.add_edge(u, v) # Build a real biochemical reaction arrow!
                                    
        except Exception as e:
            print(f"解析 {path_id} KGML 發生異常: {e}")
            
    # ─── Step 3: safe fallback ───
    # If parsing yields no edges at all (e.g. the pathway's structure is undefined in KEGG),
    # connect the nodes into a line so topology analysis still has a basic baseline to run on
    if G.number_of_edges() == 0 and len(compounds) >= 2:
        for i in range(len(compounds) - 1):
            G.add_edge(compounds[i], compounds[i+1])
            
    return G
    
# download_smpdb_metabolite_gmt()

if __name__ == "__main__":
    # From backend/: python -m src.graph_agent.use_tool.download_path_db
    download_kegg_metabolite_gmt(
        os.path.join(os.path.dirname(__file__), "..", "database", "kegg_metabolites_hsa.gmt")
    )


