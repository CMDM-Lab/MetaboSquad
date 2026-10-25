
import pandas as pd
from langchain.tools import tool
from pathlib import Path
from src.graph_agent.use_tool.parameter_knoeledge import ANALYSIS_KNOWLEDGE
import docker
import os, shutil, uuid

def extract_schema_and_config(
    file, 
    group_name: str, 
    paired: bool, 
    label_is_continuous: bool,
) -> dict:
    """Read a CSV file and return its column structure plus the matching R config."""
    # 1. Get the absolute path of the project root (hard-code it or read it from an environment variable)
    BASE_DIR = Path(__file__).resolve().parent.parent # Adjust to your directory layout
    
    # 2. Clean the path: strip the leading "/", otherwise Path treats it as the filesystem root
    clean_path = file.lstrip("/") 
    
    # 3. Build the real on-disk path
    full_path = BASE_DIR / clean_path
    
    print(f"Agent 嘗試讀取的實體路徑為: {full_path}")

    if not full_path.exists():
        return {f"csv_summary":"找不到檔案，請確認路徑 {full_path} 是否正確"}

    # 4. Only then hand it to LangChain or Pandas
    # loader = CSVLoader(file_path=str(full_path))
    if full_path is not None:
        try:
            df = pd.read_csv(full_path)
            # --- Step 1: detect data orientation (Direction Detection) ---
            # Assume features usually number more than 50 and far exceed the samples
            is_transposed = False
            if df.shape[0] > df.shape[1] and df.shape[0] > 50:
                is_transposed = True
                # If samples are in columns, transpose so the group can be detected
                analysis_df = df.set_index(df.columns[0]).T 
            else:
                analysis_df = df

            # --- Step 2: find the group column (Group Detection) ---
            group_col = None

            # --- 2.1 user-specified ---
            if group_name:
                for col in analysis_df.columns:
                    if group_name.lower() in str(col).lower():
                        group_col = col
                        break

            # --- 2.2 keyword search ---
            if group_col is None:
                keywords = ["group", "class", "condition", "type"]
                for col in analysis_df.columns:
                    col_lower = str(col).lower()
                    if any(k in col_lower for k in keywords):
                        group_col = col
                        break

            # --- 2.3 auto-detect ---
            if group_col is None:
                candidate_cols = []

                for col in analysis_df.columns:
                    series = analysis_df[col]

                    # ❌ Exclude numeric columns
                    if pd.api.types.is_numeric_dtype(series):
                        continue

                    unique_vals = series.dropna().unique()
                    unique_count = len(unique_vals)

                    # ❌ Exclude columns with too many levels (avoid continuous values)
                    if unique_count < 2 or unique_count > 10:
                        continue

                    candidate_cols.append((col, unique_count))

                # Pick the one with the fewest levels
                if candidate_cols:
                    candidate_cols.sort(key=lambda x: x[1])
                    group_col = candidate_cols[0][0]
            
            # --- Step 3: extract information ---
            group_names = []
            group_count = 0
            group_summary_text = ""

            if group_col is not None:
                group_stats = analysis_df[group_col].value_counts(dropna=True).to_dict()

                group_names = list(group_stats.keys())
                group_count = len(group_names)

                group_summary_text = ", ".join(
                    [f"{str(name)} (n={count})" for name, count in group_stats.items()]
                )

                group_info = (
                    f"'{group_col}' (共 {group_count} 組："
                    f"{', '.join(map(str, group_names))}，各組分佈：{group_summary_text})"
                )
            else:
                group_info = "未偵測到分組欄位"
        

            # === Step 4: summary ===
            summary = f"""成功解析 CSV！
            - 偵測方向: {"每一個 column 是一個樣本" if is_transposed else "每一個 row 是一個樣本"}
            - 總樣本數: {analysis_df.shape[0]}
            - 總特徵數: {analysis_df.shape[1]}
            - 分組欄位: {group_info}
            """

            # --- Step 4: decide parameters ---    
            # -------------------------
            # 2️⃣ InitDataObjects
            # -------------------------
            paired_val = "TRUE" if paired else "FALSE"

            # -------------------------
            # 3️⃣ Read.TextData
            # -------------------------
            direction_prefix = "col" if is_transposed else "row"
            pair_suffix = "p" if paired else "u"
            format_val = f"{direction_prefix}{pair_suffix}"

            # 🔥 Infer label.type automatically
            label_type = "cont" if label_is_continuous else "disc"

            config_by_data = {
                "file_path": file,
                "paired": paired_val,
                "format": format_val,
                "label.type": label_type,
            }

            return {
                "csv_summary": summary,
                "group_count": group_count,
                "config_by_data":config_by_data
            }

        except Exception as e:
            return {"csv_summary": f"錯誤：{e}"}#, "schema": []}
    return {"csv_summary": "尚未上傳檔案"}#, "schema": []}

def diagnose_data_and_recommend(
    group_count: int,
) -> dict: # Changed return type hint
    """
    Diagnose the data characteristics and return the recommended analysis methods.
    """
    recommendations = []


    if group_count == 2:
        recommendations.append({
            "analysis": "fold-change",
            "reason": "計算兩組間倍數變化，快速篩選差異特徵",
        })
        recommendations.append({
            "analysis": "t-test",
            "reason": "兩組統計顯著性檢定",
        })
        recommendations.append({
            "analysis": "volcano",
            "reason": "同時視覺化倍數變化與統計顯著性",
        })

    if group_count >= 3:
        recommendations.append({
            "analysis": "anova",
            "reason": f"多組（{group_count} 組）比較使用 ANOVA",
        })

    recommendations.append({
        "analysis": "pca",
        "reason": "探索樣本整體分佈結構，是任何分析的基礎探索步驟",
    })


    # recommendations.append({
    #     "analysis": "pls-da",
    #     "reason": "Supervised classification; finds the feature combination that maximises between-group differences",
    # })

    return {
        "recommendations": recommendations,
    }

def get_default_config(module_list: list, config_by_data: dict) -> dict:
    """
    Extract each module's default parameter values from ANALYSIS_KNOWLEDGE,
    merge in config_by_data (auto-detected parameters), and return the full config dict
    """
    # module_names = [
    #     m['analysis'] if isinstance(m, dict) else m
    #     for m in module_list
    # ]

    category_data = ANALYSIS_KNOWLEDGE.get("one-factor-statistics", {})

    # Make sure preprocessing comes first
    essential_mod = "preprocessing"
    if essential_mod in module_list:
        module_list.remove(essential_mod)
    module_list.insert(0, essential_mod)

    # Start from config_by_data and layer later parameters on top
    final_config = dict(config_by_data)

    for module in module_list:
        data = category_data.get(module, {})
        params = data.get("parameter_knowledge", {})

        for p_name, p_info in params.items():
            # Auto-detected parameters are already in config_by_data; skip
            if p_name in config_by_data:
                continue
            # Fill in the default value
            if "default" in p_info:
                final_config[p_name] = p_info["default"]

    return final_config

def generate_combined_code(module_list, config):
    """
    Concatenate the code of several modules and substitute parameters with the user's choices.
    all_user_values: a large dict containing config by data and the values obtained from `get_modules_schema`
    """
    category_data = ANALYSIS_KNOWLEDGE.get("one-factor-statistics", {})
    combined_code = []
    
    # Safe formatter
    import string
    class FullKeyFormatter(string.Formatter):
        def get_field(self, field_name, args, kwargs):
            # Always look up the dict directly; do not split on dots (.) or indexes ([])
            return kwargs[field_name], field_name
    
    available_modules = set(category_data.keys())

    # Check for invalid modules
    invalid_modules = [m for m in module_list if m not in available_modules]

    if invalid_modules:
        return {
            "error": "invalid_module",
            "invalid_modules": invalid_modules,
            "available_modules": sorted(list(available_modules))
        }
    
    essential_mod = "preprocessing"

    # 3. If preprocessing is already in the list, remove it first (avoid duplicates)
    if essential_mod in module_list:
        module_list.remove(essential_mod)
    
    # 4. Insert preprocessing at index 0
    module_list.insert(0, essential_mod)

    for mod_name in module_list:
        module = category_data.get(mod_name)
        if not module:
            continue
            
        template = module.get("full_code", "")
        # Run the substitution for this module
        formatter = FullKeyFormatter()
        processed_code = formatter.vformat(template, [], config)
        combined_code.append(f"# --- Module: {mod_name} ---")
        combined_code.append(processed_code)
    
    return "\n".join(combined_code)


def run_with_timeout(client, timeout_sec=120, **kwargs):
    container = None
    try:
        container = client.containers.create(**kwargs)
        container.start()

        result = container.wait(timeout=timeout_sec)

        logs = container.logs(stdout=True, stderr=True).decode("utf-8")

        if result["StatusCode"] != 0:
            raise docker.errors.ContainerError(
                container,
                result["StatusCode"],
                kwargs.get("command"),
                kwargs.get("image"),
                logs
            )

        return logs, None

    except Exception as e:
        return None, str(e)

    finally:
        if container:
            try:
                container.stop(timeout=5)
            except:
                pass
            try:
                container.remove(force=True)
            except:
                pass


def run_r_code(r_code,  file_name):
    """
        Concatenate the code of several modules and substitute parameters with the user's choices, then run the R script produced by `generate_combined_code` in an isolated docker environment; on error, return the error message
    """


    job_id = uuid.uuid4().hex
    work_dir = Path(os.path.abspath(f"temp_{job_id}"))
    work_dir.mkdir(parents=True, exist_ok=True)
    # The container runs as root, but cap_drop=["ALL"] below removes CAP_DAC_OVERRIDE,
    # so root inside the container has to obey normal permission bits. work_dir belongs
    # to the user running uvicorn (e.g. uid 1000) with mode 775, so root falls into
    # "other" with r-x -> R cannot create any output file and the analysis fails on write.
    # Docker Desktop on Windows mediates bind mounts through a VM with effectively open
    # permissions, so the problem does not show up when developing on Windows.
    # Use 0o777 rather than adding back cap_add=["DAC_OVERRIDE"]: the latter would let the
    # container bypass every file permission check; here it only needs to write into this
    # one short-lived temp directory.
    work_dir.chmod(0o777)

    # Wrap execution in an inner function so it can be re-run after an error is detected
    def execute_docker(current_code, allow_network=False):
        r_script_path = work_dir / "script.R"
        with open(r_script_path, "w", encoding="utf-8") as f:
            f.write(current_code)
        
        client = docker.from_env()
        # Note: network_disabled must be False to install packages
        return run_with_timeout(
            client,
            image="meta_image:v3",
            command=["Rscript", "script.R"],
            volumes={
                str(work_dir): {"bind": "/workspace", "mode": "rw"},
                str(Path(os.path.abspath("uploads"))): {"bind": "/uploads", "mode": "ro"},
            },
            working_dir="/workspace",
            # This used to be 512m, and the demo data (12 samples x 410 features) hit OOM: the
            # container died with exit 137 (SIGKILL), and it died in the plotting module **after**
            # the t-test, so R's statistics actually finished but the report was never produced.
            # The visible symptom looks nothing like a memory problem -- analysis_result.success=False,
            # result_files=[], and the user only sees "Analysis results CSV not found.".
            # Measured 2026-08-04: 512m -> exit 137 (14 files); 768m/1g/2g -> exit 0 (22 files).
            # 2g leaves headroom: user-uploaded data may be much larger.
            # This value does not affect any analysis output (R's numbers are deterministic); it only
            # decides whether the process gets killed -- the same kind of environment fix as
            # work_dir.chmod(0o777). The lower bound is guarded by tests/test_r_container_limits.py.
            mem_limit="2g",
            network_disabled=not allow_network, # Toggle network access dynamically
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
        )

    try:
        # First run
        logs, timeout_err = execute_docker(r_code, allow_network=False)

        if timeout_err:
            return False, timeout_err

        output = logs.decode("utf-8") if isinstance(logs, bytes) else logs
        
        # --- [error-handling extension] ---
        # Detect whether R's error message reports a missing ellipse package
        import re

        def detect_missing_packages(output: str):
            pattern = r"there is no package called ['\"]([^'\"]+)['\"]"
            return list(set(re.findall(pattern, output)))


        # --- Auto-install missing packages ---
        missing_pkgs = detect_missing_packages(output)

        if missing_pkgs:
            print(f"偵測到缺少套件：{missing_pkgs}，嘗試自動安裝...")

            install_code = "\n".join([
                f'if(!require("{pkg}", quietly=TRUE)) install.packages("{pkg}", repos="https://cloud.r-project.org/")'
                for pkg in missing_pkgs
            ]) + "\n"

            new_r_code = install_code + r_code
            # Second run: enable network access for the installation
            logs, timeout_err = execute_docker(new_r_code, allow_network=True)

            if timeout_err:
                return False, f"安裝套件逾時: {timeout_err}"

            output = logs.decode("utf-8") if isinstance(logs, bytes) else logs
            
        # --- [end of error handling] ---
        
        uploads_dir = Path(os.path.abspath("uploads"))
        uploads_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        file_name_only = Path(file_name).stem # Pathlib is more concise
        # job_upload_dir = uploads_dir / f"{file_name_only}_{timestamp}"
        job_upload_dir = uploads_dir /"output"/"analysis"/ f"{file_name_only}_{timestamp}"
        job_upload_dir.mkdir(parents=True, exist_ok=True)

        # Find all generated files (excluding the input script.R)
        produced_files = [
            f for f in work_dir.iterdir() 
            if f.is_file() and f.name != "script.R"
        ]

        if not produced_files:
            return False, f"找不到任何輸出檔案\n\nOutput:\n{output}"

        # Copy everything to uploads
        saved_paths = []
        project_root = Path(os.path.abspath(".")).parent
        for file_path in produced_files:
            dest_path = job_upload_dir / file_path.name
            shutil.copy2(file_path, dest_path)
            
            # Compute the relative path inside the loop and make sure it is posix style (web slashes)
            try:
                rel_p = dest_path.relative_to(project_root)
                web_path = f"/{rel_p.as_posix()}"
            except ValueError:
                # If it is not under project_root, fall back
                web_path = f"/uploads/{dest_path.name}"

            saved_paths.append({
                "filename": file_path.name,
                "path": web_path,
                "type": file_path.suffix.lstrip(".")
            })

        return True, {
            "files": saved_paths,
            "output": output
        }

    except docker.errors.ContainerError as e:
        # ContainerError's error content is in e.stderr or the logs
        stderr = e.stderr.decode("utf-8") if isinstance(e.stderr, bytes) else str(e)
        
        # Handle everything through detect_missing_packages
        missing_pkgs = detect_missing_packages(stderr)
        if missing_pkgs:
            print(f"[ContainerError] 偵測到缺少套件：{missing_pkgs}，嘗試安裝...")
            install_code = "\n".join([
                f'if(!require("{pkg}", quietly=TRUE)) install.packages("{pkg}", repos="https://cloud.r-project.org/")'
                for pkg in missing_pkgs
            ]) + "\n"
            logs, timeout_err = execute_docker(install_code + r_code, allow_network=True)
            if not timeout_err:
                output = logs.decode("utf-8") if isinstance(logs, bytes) else logs
                # Continue with the rest of the file-collection logic...
        
        return False, f"R 執行錯誤：\n{stderr}"

    except docker.errors.ImageNotFound:
        return False, "找不到 Docker image：metabo_docker:v1"

    except docker.errors.APIError as e:
        return False, f"Docker API 錯誤：{str(e)}"

    except Exception as e:
        return False, f"未預期錯誤：{str(e)}"

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
            
@tool
def recommend_and_analysis(
    file,
    group_name: str,
    paired: bool, 
    label_is_continuous: bool
) -> dict:
    """
    Recommend analysis methods base on the characteristics of the data provided, determine preprocessing parameters, and perform analysis.
    """
    try:
        extract_schema = extract_schema_and_config(file, group_name, paired, label_is_continuous)
    except Exception as e:
        return {"csv_summary": f"錯誤：{e}"}

    group_count = extract_schema.get("group_count")
    summary = extract_schema.get("csv_summary")
    config_by_data = extract_schema.get("config_by_data")

    try:
        diagnosis = diagnose_data_and_recommend(group_count)
    except Exception as e:
        return {"recommend": f"錯誤：{e}"}

    # Variable renamed from `result` to `diagnosis`: previously the
    # `success, result = run_r_code(...)` below overwrote it completely, so the returned
    # `"recommend"` was actually R's list of output files, and the per-module `reason`
    # ("why t-test was chosen") computed by diagnose_data_and_recommend was thrown away --
    # which is exactly what the report most lacked.
    recommendations = diagnosis.get("recommendations") or []
    module_list = recommendations
    module_names = [
        m['analysis'] if isinstance(m, dict) else m
        for m in module_list
    ]

    try:
        config = get_default_config(module_names, config_by_data)
    except Exception as e:
        return {"get_modules": f"錯誤：{e}"}
    
    try:
        r_code = generate_combined_code(module_names, config)
    except Exception as e:
        return {"generate_code": f"錯誤：{e}"}

    
    r_code = r_code.replace('"uploads/', '"/uploads/').replace("'uploads/", "'/uploads/")

    try:
        success, run_result = run_r_code(r_code, file)
    except Exception as e:
        return {"run_r_code": f"錯誤：{e}"}

    all_paths=[]

    if success:
        all_paths = [f["path"] for f in run_result["files"]]

    return {
    "success": success,
    "summary": summary,      # Raw-data level
    "recommend": recommendations,  # Decision/recommendation level (per-module analysis + reason)
    # R's raw output / error message. A separate key rather than stuffed into recommend:
    # on failure this holds docker's full output, and the 2026-08-04 OOM (exit 137) was only
    # diagnosed thanks to it; that diagnostic ability must not be lost by fixing recommend.
    "run_log": run_result,
    "config" : config,
    "r_code": r_code,
    "result_files": all_paths
    }

# r=recommend_and_analysis("uploads/csv/pca_input_1003.csv", "group", False, False)
# output_file = "./re.json"
# import json

# with open(output_file, "w", encoding="utf-8") as f:
#     json.dump(r, f, ensure_ascii=False, indent=2)