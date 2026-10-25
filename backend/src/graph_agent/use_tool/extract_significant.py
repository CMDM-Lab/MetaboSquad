import pandas as pd
from langchain.tools import tool
from pathlib import Path
import re

@tool
def extract_significant(file) -> list:
    """Read a CSV file and return the list of metabolites with significant differences"""
    # 1. Get the absolute path of the project root (hard-code it or read it from an environment variable)
    BASE_DIR = Path(__file__).resolve().parent.parent # Adjust to your directory layout
    
    # 2. Clean the path: strip the leading "/", otherwise Path treats it as the filesystem root
    clean_path = file.lstrip("/") 
    
    # 3. Build the real on-disk path
    full_path = BASE_DIR / clean_path
    
    print(f"Agent 嘗試讀取的實體路徑為: {full_path}")

    if not full_path.exists():
        return f"錯誤：找不到檔案，請確認路徑 {full_path} 是否正確"

    try:
        df = pd.read_csv(full_path)
        df.columns.values[0] = "Feature"
        filtered = df[df["FDR"] < 0.05]

        results = []

        def remove_adduct(name):
            # Strip adduct suffixes like [M+H]+ and [M-H]-
            return re.sub(r"\[.*?\][+-]?", "", name).strip()
        def split_compounds(name):
            return [n.strip() for n in name.split("|")]

        for name in filtered["Feature"]:
            clean = remove_adduct(name)
            compounds = split_compounds(clean)
            results.extend(compounds)

        return list(dict.fromkeys(results))
    except Exception as e:
        return {"csv_summary": f"錯誤：{e}"}


