import json
import os
import re  # Fix: add the missing re module
import requests
import time

from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field 
from typing import Literal, Any        
# ── Pydantic Models ──────────────────────────────────────────────────────────

from src.graph_agent.pydantic_models import FilterResult, ExtractResult


llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

# ===== Ollama =====
# pip install langchain-ollama
# from langchain_ollama import ChatOllama 
# llm = ChatOllama(
#     model="gemma4:26b",  # the model name or tag in Ollama
#     temperature=0,
#     # base_url="http://remote-server:11434" # set this if Ollama runs on a remote server
# )

# ── Tools ────────────────────────────────────────────────────────────────────

def title_filter_tool(papers: list[dict], question: str) -> list[dict]:
    """
    Score literature titles for relevance and return whether each one is relevant.
    """
    structured_llm = llm.with_structured_output(FilterResult)

    papers_json = json.dumps(
        [{"idx": i, "title": p["title"]}
         for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    resp = structured_llm.invoke([
        SystemMessage(content=(
            "You are a scientific literature screening assistant. "
            "Given a research question and a list of paper titles, classify each paper. "
            "Rules: "
            "- Output 'relevant' if the title suggests the paper studies the relationship "
            "between the exposure and outcome in the research question. "
            "- Output 'irrelevant' if the title is clearly unrelated. "
            "- When in doubt, prefer 'relevant' over 'irrelevant' to avoid missing important papers."
        )),
        HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
    ])

    rating_map = {r.idx: r for r in resp.results}

    for i, paper in enumerate(papers):
        rating = rating_map.get(i)
        if rating:
            paper["title_decision"] = rating.decision
            paper["reason"] = rating.reason
        else:
            paper["title_decision"] = "relevant"  # fallback: keep by default
            paper["reason"] = "N/A"

    return sorted(
        papers,
        key=lambda x: 0 if x.get("title_decision") == "relevant" else 1
    )

def abstract_filter_tool(papers: list[dict], question: str) -> list[dict]:
    """Screen literature abstracts for relevance (binary classification)."""

    structured_llm = llm.with_structured_output(FilterResult)

    papers_json = json.dumps(
        [{"idx": i, "abstract": p["abstract"]}
         for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    resp = structured_llm.invoke([
        SystemMessage(content=(
            "You are a scientific literature screening assistant. "
            "Given a research question and a list of paper abstracts, classify each paper. "
            "Rules: "
            "- Output 'relevant' if the abstract suggests the paper studies the relationship "
            "between the exposure and outcome in the research question. "
            "- Output 'irrelevant' if the abstract is clearly unrelated. "
            "- When in doubt, prefer 'relevant' over 'irrelevant' to avoid missing important papers."
        )),
        HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
    ])

    rating_map = {r.idx: r for r in resp.results}

    for i, paper in enumerate(papers):
        rating = rating_map.get(i)
        if rating:
            paper["abstract_decision"] = rating.decision
            paper["reason"] = rating.reason
        else:
            paper["abstract_decision"] = "relevant"  # fallback: keep by default
            paper["reason"] = "N/A"

    return sorted(
        papers,
        key=lambda x: 0 if x.get("title_decision") == "relevant" else 1
    )



def abstract_extract(papers: list[dict], question: str) -> list[dict]:
    """Extract structured data from literature abstracts."""

    structured_llm = llm.with_structured_output(ExtractResult)

    papers_json = json.dumps(
        [{"idx": i, "abstract": p["abstract"]}
         for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    resp = structured_llm.invoke([
        SystemMessage(content=("""
        You are a biomedical research extraction assistant. Your task is to extract high-quality structured information from a peer-reviewed abstract that has already been verified as highly relevant to the research question.

        [Task Instruction]
        Analyze the provided abstract and extract the core PECO (Population, Exposure, Comparison, Outcome) elements and study characteristics into a structured format. 

        Focus strictly on these high-level key fields:
        - population: The target participants or animals studied (e.g., age group, species, geographic region).
        - exposure: The chemical, environmental factor, or biological agent being investigated.
        - outcome: The clinical health outcomes, diseases, or molecular biomarkers measured.
        - study_design: The methodology used (e.g., Cohort, Case-control, Cross-sectional, RCT, In vivo/In vitro, Review).
        - sample_size: Total number of participants, samples, or animals involved.
        - key_finding: One concise sentence summarizing the main biological, physiological, or statistical result.
        - direction: Classify the relationship's direction based on the nature of the Research Question:
        * For exposure/harm-related questions: 
            - "positive" (exposure significantly increases risk, disease incidence, or harm)
            - "negative" (exposure decreases risk or provides protection)
            - "neutral" (no statistically significant association, or levels are within safe guidance limits)
        * For biomarker/mechanism-related questions:
            - "positive" (exposure significantly UPREGULATES or increases the biomarker level)
            - "negative" (exposure significantly DOWNREGULATES or decreases the biomarker level)
            - "neutral" (no statistically significant change or difference in the biomarker level)
        - limitation: Any weak points mentioned in the abstract (e.g., small sample size, potential bias, lack of direct measurement). If none, leave empty "".

        [Data Extraction Rules]
        1. Base your extraction STRICTLY on the text provided in the abstract. Do not extrapolate.
        2. If a specific field is not explicitly mentioned or cannot be inferred from the abstract, return an empty string "". Do not hallucinate or guess.
        """
        )),
        HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
    ])

    extract_map = {r.idx: r for r in resp.results}

    for i, paper in enumerate(papers):
        extract = extract_map.get(i)
        if extract:
            paper.update({
                "population":   extract.population,
                "exposure":     extract.exposure,
                "outcome":      extract.outcome,
                "study_design": extract.study_design,
                "sample_size":  extract.sample_size,
                "key_finding":  extract.key_finding,
                "direction":    extract.direction,
                "limitation":   extract.limitation,
            })
        else:
            paper.update({
                "population": "", "exposure": "", "outcome": "",
                "study_design": "", "sample_size": "", "key_finding": "",
                "direction": "neutral", "limitation": "",
            })

    return papers


def _generate_apa_marker(paper):
    authors_str = paper.get("authors", "").strip()
    year = str(paper.get("year", "n.d.")).strip()
    
    if not authors_str:
        # If there is no author, use the first few words of the title instead
        short_title = paper.get("title", "")[:20] + "..."
        return f"({short_title}, {year})"
    
    # Split the author list on commas
    author_list = [a.strip() for a in authors_str.split(",") if a.strip()]
    
    if len(author_list) == 1:
        last_name = author_list[0].split(" ")[0]
        return f"({last_name}, {year})"
    elif len(author_list) == 2:
        last_name1 = author_list[0].split(" ")[0]
        last_name2 = author_list[1].split(" ")[0]
        return f"({last_name1} & {last_name2}, {year})"
    else:
        # Three or more authors: use et al.
        last_name1 = author_list[0].split(" ")[0]
        return f"({last_name1} et al., {year})"



def summary_tool(papers: list[dict], question: str) ->  str:
    """
    Take the literature and the question, and generate a summary.
    """

    papers_json = json.dumps(
        [{"idx": i, "key_finding": p["key_finding"], "URL": p["pm_url"], "apa_marker": _generate_apa_marker(p)}
         for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    resp = llm.invoke([
        SystemMessage(content=(
        """
        You are a metabolomics research assistant. Your task is to synthesize a summary to answer the user's question based strictly on the provided literature key findings.
        Every single sentence in your response must be cited.
        At the end of each sentence, append its corresponding `[apa_marker]` formatted as a clickable markdown hyperlink pointing to its specific URL. (Format: [apa_marker](url)).
        Do NOT fabricate, extrapolate, or guess any information. Base your response 100 percent on the provided key finding.
        CRITICAL INSTRUCTION: You MUST respond exclusively in English. Do not use any other language regardless of the input language.
        """
        )),
        HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
    ])

    return resp.content

def _reconstruct_abstract(inverted_index: Any) -> str:
    """Private helper: rebuild plain abstract text from OpenAlex's inverted index"""
    if not inverted_index or not isinstance(inverted_index, dict):
        return "N/A"
    try:
        word_positions = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions[pos] = word
        sorted_words = [word_positions[p] for p in sorted(word_positions.keys())]
        return " ".join(sorted_words)
    except Exception:
        return "N/A"

@tool
def search_openalex_abstracts(id_list: list[str]) -> list[dict[str, Any]]:
    """Query OpenAlex for abstracts of specific OpenAlex IDs in batches and reconstruct them."""
    if not id_list:
        return []
        
    email = os.getenv("EMAIL")
    headers = {"Accept": "application/json"}
    if email:
        headers["User-Agent"] = f"mailto:{email}" # join the Polite Pool for better connection quality

    formatted_results = []
    
    # Batch preemptively: OpenAlex filter URLs have a length limit; 25 works per batch is safest
    batch_size = 25
    
    for chunk_start in range(0, len(id_list), batch_size):
        batch_ids = id_list[chunk_start : chunk_start + batch_size]
        
        # Build the OpenAlex batch filter syntax, e.g. openalex_id:W123|W456|W789
        # Make sure the ID format is correct (users sometimes pass a full URL; keep only the trailing short ID)
        clean_ids = [str(i).split("/")[-1].strip() for i in batch_ids]
        id_filter = "|".join(clean_ids)
        
        url = "https://api.openalex.org/works"
        params = {
            "filter": f"openalex_id:{id_filter}",
            "per_page": len(clean_ids)
        }
        
        for attempt in range(3): # same 3-retry mechanism as PubMed
            try:
                print(f"[OpenAlex] 正在批次抓取摘要 (進度: {chunk_start}/{len(id_list)})...")
                response = requests.get(url, params=params, headers=headers, timeout=20)
                response.raise_for_status()
                
                data = response.json()
                works = data.get("results", [])
                
                for work in works:
                    openalex_id = work.get("id", "").split("/")[-1]
                    title = work.get("title", "")
                    
                    # call the rebuild helper
                    inverted_index = work.get("abstract_inverted_index")
                    abstract = _reconstruct_abstract(inverted_index)
                    
                    formatted_results.append({
                        "openalex_id": openalex_id,
                        "title": title,
                        "abstract": abstract,
                        "doi": work.get("doi"),
                        "pmid": work.get("ids", {}).get("pmid")
                    })
                
                break # got the data, leave the retry loop
                
            except Exception as e:
                if attempt == 2: 
                    print(f"[Error] OpenAlex 批次擷取摘要失敗: {e}")
                time.sleep(2) # on error, wait briefly and retry
                
    return formatted_results

# result = search_openalex('"smoke"AND"cancer"')
# print (result)
# view the result directly
# https://api.openalex.org/works?search=smoke+cancer&filter=type:article&per_page=5&cursor=*

    # formatted_results = []
    # for it in all_items:
    #     try:
    #         title = it.get("title") or "N/A"
            
    #         authorships = it.get("authorships", [])
    #         author_names = [a.get("author", {}).get("display_name", "") for a in authorships[:3]]
    #         author_names = [name for name in author_names if name]
    #         authors = ", ".join(author_names) if author_names else "N/A"
    #         if len(authorships) > 3:
    #             authors += " et al."
                
    #         journal = it.get("primary_location", {}).get("source", {}).get("display_name") or "N/A"
    #         year = str(it.get("publication_year")) if it.get("publication_year") else "N/A"
            
    #         ids = it.get("ids", {})
    #         pmid = ids.get("pmid", "").replace("https://pubmed.ncbi.nlm.nih.gov/", "")
    #         pmid = pmid if pmid else "N/A"
            
    #         abstract = "N/A"
    #         inverted_index = it.get("abstract_inverted_index")
    #         if inverted_index and isinstance(inverted_index, dict):
    #             word_positions = {}
    #             for word, positions in inverted_index.items():
    #                 for pos in positions:
    #                     word_positions[pos] = word
    #             sorted_words = [word_positions[p] for p in sorted(word_positions.keys())]
    #             abstract = " ".join(sorted_words)

    #         doi = it.get("doi")
    #         id = it.get("id")

    #         formatted_results.append({
    #             "title": title,
    #             "authors": authors,
    #             "journal": journal,
    #             "year": year,
    #             "pmid": pmid,
    #             "abstract": abstract,
    #             "source": "openalex_semantic",
    #             "openalex_id": id,
    #             "doi": doi
    #         })
    #     except Exception as e:
    #         continue

# To do the reverse (see which earlier works this paper references),
# change the filter parameter in the code from f"cites:{clean_id}" to f"openalex:{clean_id}".
@tool
def get_incoming_citations_with_abstract(target_work_id: str, max_results: int = 5) -> list[dict]:
    """
    Fetch all other works that cite target_work_id, extract their abstracts, and align them with the PubMed format.
    
    :param target_work_id: OpenAlex ID of the target paper (e.g. "W2741809807")
    :param max_results: maximum number of works to return
    """
    API_KEY = os.getenv("OPENALEX_API_KEY")
    url = "https://api.openalex.org/works"
    
    # Make sure the ID format is correct (strip any URL prefix)
    clean_id = target_work_id.split("/")[-1]
    
    # Set parameters: use filter=cites:ID from Step 3, sorted by publication date (newest first)
    per_page = min(max_results, 100)
    params = {
        "filter": f"cites:{clean_id}",
        "sort": "publication_date:desc",
        "per_page": per_page,
        "cursor": "*"
    }

    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    else:
        params["mailto"] = os.getenv("EMAIL")

    all_citations = []
    
    try:
        print(f"正在尋找引用了 {clean_id} 的文獻 (上限: {max_results} 筆)...")
        while len(all_citations) < max_results:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"錯誤: API 回傳狀態碼 {response.status_code}, 內容: {response.text}")
                break
                
            data = response.json()
            results = data.get("results", [])
            if not results:
                break
                
            all_citations.extend(results)
            
            if len(all_citations) >= max_results:
                all_citations = all_citations[:max_results]
                break
                
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
            time.sleep(0.2)
            
    except Exception as e:
        print(f"連線或處理發生異常: {e}")
        return []

    # Format the output (align with PubMed format + rebuild abstract from inverted index)
    formatted_results = []
    for it in all_citations:
        try:
            title = it.get("title") or "N/A"
            
            # Author parsing (first three + et al.)
            authorships = it.get("authorships", [])
            author_names = [a.get("author", {}).get("display_name", "") for a in authorships[:3]]
            author_names = [name for name in author_names if name]
            authors = ", ".join(author_names) if author_names else "N/A"
            if len(authorships) > 3:
                authors += " et al."
                
            journal = it.get("primary_location", {}).get("source", {}).get("display_name") or "N/A"
            year = str(it.get("publication_year")) if it.get("publication_year") else "N/A"
            
            # PMID extraction
            ids = it.get("ids", {})
            pmid = ids.get("pmid", "").replace("https://pubmed.ncbi.nlm.nih.gov/", "") if ids.get("pmid") else "N/A"
            
            # Key step: rebuild OpenAlex's inverted-index abstract into normal text
            abstract = "N/A"
            inverted_index = it.get("abstract_inverted_index")
            if inverted_index and isinstance(inverted_index, dict):
                word_positions = {}
                for word, positions in inverted_index.items():
                    for pos in positions:
                        word_positions[pos] = word
                sorted_words = [word_positions[p] for p in sorted(word_positions.keys())]
                abstract = " ".join(sorted_words)

            doi = it.get("doi")
            id = it.get("id")

            formatted_results.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "pmid": pmid,
                "abstract": abstract,
                "source": "openalex_semantic",
                "openalex_id": id,
                "doi": doi
            })
        except Exception as e:
            continue

    return formatted_results

# result = get_incoming_citations_with_abstract("W2741809807")
# print (result)

@tool
def get_openalex_id_by_external_id(id_string: str) -> Optional[str]:
    """
    General converter: detect whether the input is an OpenAlex ID, PMID, or DOI, and convert it to an OpenAlex short ID (e.g., W2969315024)
    
    Supported formats:
    - OpenAlex ID: "W2969315024", "https://openalex.org/W2969315024"
    - PMID: "31439243", "pmid:31439243"
    - DOI: "10.1016/j.jbiotec.2019.08.012", "https://doi.org/10.1016/..."
    """
    id_string = id_string.strip()
    email = os.getenv("EMAIL", "")
    headers = {"User-Agent": f"mailto:{email}"} if email else {}
    
    # ── 0. New: check whether it is already an OpenAlex ID ───────────────────────
    # Supports "W12345678" or "https://openalex.org/W12345678"
    if "openalex.org" in id_string.lower() or re.match(r"^W\d+$", id_string, re.IGNORECASE):
        # Clean up and extract the trailing short ID (e.g. W2969315024)
        clean_id = id_string.split("/")[-1].strip().upper()
        # Check again that the format is W + digits
        if re.match(r"^W\d+$", clean_id):
            print(f"[OpenAlex] 輸入已是 OpenAlex ID ({clean_id})，直接返回，免除 API 請求。")
            return clean_id

    # ── 1. Check whether it is a DOI ─────────────────────────────────────────────
    if "10." in id_string or "doi.org" in id_string:
        # Clean up the DOI, keeping only the part starting with 10.xxxx
        clean_doi = id_string.replace("https://doi.org/", "").replace("http://doi.org/", "")
        url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
        id_type = "DOI"
        
    # ── 2. Check whether it is a PMID ────────────────────────────────────────────
    else:
        # Remove non-digit characters, keeping only the digits
        clean_pmid = re.sub(r"\D", "", id_string)
        if not clean_pmid:
            print(f"[Error] 無法識別的識別碼格式: {id_string}")
            return None
        url = f"https://api.openalex.org/works/pmid:{clean_pmid}"
        id_type = "PMID"
        
    # ── 3. Online conversion logic ───────────────────────────────────────────────
    try:
        print(f"[OpenAlex] 正在透過 {id_type} 檢索 OpenAlex ID...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            openalex_url_id = response.json().get("id") # returns "https://openalex.org/W2969315024"
            if openalex_url_id:
                short_id = openalex_url_id.split("/")[-1]
                return short_id
        else:
            print(f"[Warning] OpenAlex 找不到對應的文獻。狀態碼: {response.status_code}")
            
    except Exception as e:
        print(f"[Error] 轉換識別碼時發生異常: {str(e)}")
        
    return None

@tool
def search_openalex_fulltext(
    keyword: str,
    openalex_id: str | None = None,  # if set, snowball; if empty, broad search over the whole index
    direction: str = "forward"       # "forward" or "backward"
) -> list[dict[str, Any]]:
    """
    OpenAlex exhaustive retrieval tool (uses the native search, which covers full text)
    
    1. Auto mode: with openalex_id, snowball in both directions; without it, broad search over the whole index.
    2. Full pagination: uses the Cursor mechanism to fetch every matching work, not capped at 200.
    3. Semantic ranking: uses the top-level search parameter so results are ranked by relevance.
    """
    endpoint = "https://api.openalex.org/works"
    keyword = keyword.strip()
    
    # 1. Initialize base parameters
    params = {
        "per_page": 200,  # use the per-request maximum for efficiency
        "cursor": "*"     # enable Cursor deep pagination
    }
    filters = []

    # ── 2. Choose the mode: snowball vs broad search ──
    is_snowball = bool(openalex_id)
    
    if is_snowball:
        clean_id = openalex_id.split("/")[-1].strip()
        if direction == "forward":
            print(f"[OpenAlex] 啟動【全量向前滾雪球】：尋找「引用」 {clean_id} 的所有文獻...")
            filters.append(f"cites:{clean_id}")
        else:
            print(f"[OpenAlex] 啟動【全量向後滾雪球】：尋找被 {clean_id} 「所引用」的所有文獻...")
            filters.append(f"referenced_works:{clean_id}")
    else:
        # Enter broad-search mode
        if not keyword:
            print("[OpenAlex Warning] 全庫廣搜模式必須提供關鍵字！")
            return []
        print(f"[OpenAlex] 啟動【全庫綜合廣搜】...")

    # ── 3. Handle search keywords and filters ──
    if keyword:
        params["search"] = keyword
        # With keywords, OpenAlex always ranks by semantic relevance to full text/abstract/title, descending
        params["sort"] = "relevance_score:desc"
    else:
        # If snowballing and the user gave no keywords (pure retrieval), rank by citation count, descending
        params["sort"] = "cited_by_count:desc"

    if filters:
        params["filter"] = ",".join(filters)

    # ── 4. Run Cursor deep-pagination retrieval ──
    email = os.getenv("EMAIL", "")
    headers = {"User-Agent": f"mailto:{email}"} if email else {}
    
    all_search_results = []
    page_count = 1
    
    # Safety limit: broad search has a huge population, so cap the page count; snowballing may fetch everything
    max_pages = 9999 if is_snowball else 5  # broad search fetches at most 5 pages (1000 works) to avoid overloading the API
    
    try:
        while page_count <= max_pages:
            print(f"-> 正在下載第 {page_count} 頁資料 (目前已累積 {len(all_search_results)} 篇)...")
            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
            
            if response.status_code != 200:
                print(f"[OpenAlex Error] 請求失敗: {response.text}")
                break
                
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                break
                
            for work in results:
                work_id = work.get("id")
                raw_pmid = work.get("ids", {}).get("pmid") or ""
                pmid = ""
                if raw_pmid:
                    pmid = str(raw_pmid).replace(
                        "https://pubmed.ncbi.nlm.nih.gov/", ""
                    ).strip("/")
                search_results_dict = {
                    "openalex_id": work_id.split("/")[-1] if work_id else None,
                    "title": work.get("title"),
                    "doi": work.get("doi"),
                    "pmid": pmid or None,
                    "year": work.get("publication_year"),
                    "oa_url": work.get("open_access", {}).get("oa_url")
                }
                # Tag the source so later LangGraph nodes can identify it
                search_results_dict["source"] = "openalex_snowball" if is_snowball else "openalex"
                all_search_results.append(search_results_dict)
            
            # Get the cursor for the next page
            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor or next_cursor == params["cursor"]:
                break
                
            params["cursor"] = next_cursor
            page_count += 1
            
        print(f"[OpenAlex Success] 打撈結束！共計 {len(all_search_results)} 篇文獻。")
        return all_search_results
        
    except Exception as e:
        print(f"[OpenAlex Exception] 發生未知異常: {e}")
        return all_search_results
# result = search_openalex_fulltext("ethyl 4-ethoxybenzoate AND VOC")
# result = search_openalex_fulltext("ethyl 4-ethoxybenzoate","W4406104185")
# print(result)


def extract_keyword_contexts(fulltext: str, keyword: str, context_paragraphs: int = 1, max_snippets: int = 10) -> list[str]:
    """
    Improved extraction tool: works per paragraph, extracts the context around keyword hits, and merges overlapping ranges.
    """
    paragraphs = [p.strip() for p in fulltext.split("\n") if p.strip()]
    
    # Build a case-insensitive regular expression
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    
    # Step 1: find the indices of all matching paragraphs
    matched_indices = [i for i, para in enumerate(paragraphs) if pattern.search(para)]
    
    if not matched_indices:
        return []
        
    # Step 2: compute the [start, end] range for each hit (half-open, convenient for slicing)
    raw_intervals = []
    for idx in matched_indices:
        start = max(0, idx - context_paragraphs)
        end = min(len(paragraphs), idx + context_paragraphs + 1)
        raw_intervals.append([start, end])
        
    # Step 3: merge overlapping or adjacent ranges (the classic Merge Intervals algorithm)
    merged_intervals = [raw_intervals[0]]
    for current in raw_intervals[1:]:
        prev_start, prev_end = merged_intervals[-1]
        curr_start, curr_end = current
        
        # If the current range starts at or before the previous range's end, they overlap or touch
        if curr_start <= prev_end:
            # Merge: set the previous range's end to the larger of the two
            merged_intervals[-1][1] = max(prev_end, curr_end)
        else:
            merged_intervals.append(current)
            
    # Step 4: slice and assemble snippets from the merged ranges
    matched_snippets = []
    for start, end in merged_intervals:
        snippet = "\n[---]Paragraph Break[---]\n".join(paragraphs[start:end])
        matched_snippets.append(snippet)
        
    # This deduplicates naturally and keeps snippets in document order (front to back)
    return matched_snippets[:max_snippets]

class MetaboliteEvaluation(BaseModel):
    is_important: bool
    role: Literal["core research subject", "significant marker", "background mention only", "low relevance"]
    score: int  # 1-5
    reason: str
    direction: Literal["positive", "negative", "neutral"]  # ← added
    key_finding: str                                        # ← added

@tool
def llm_evaluate_metabolite_importance(
    keyword: str,
    snippets: list[str]
) -> dict:
    """Have the LLM summarize the paragraphs that contain the keywords"""
    if not snippets:
        return {
            "is_important": False,
            "score": 0,
            "reason": "Keyword not found in the full text",
            "direction": "neutral",
            "key_finding": "",
        }

    combined = "\n\n=== New snippet ===\n\n".join(snippets)[:6000]

    structured_llm = llm.with_structured_output(MetaboliteEvaluation)

    resp = structured_llm.invoke([
        SystemMessage(content=(
            "You are an expert in metabolomics and bioinformatics. "
            "Evaluate the role that the target metabolite plays in the full-text snippets of the paper.\n\n"
            "Evaluation criteria:\n"
            "- Core research subject / significant marker / explicit discussion of concentration changes → is_important=true, score 4-5\n"
            "- Incidental mention in the background / unrelated table or list → is_important=false, score 1-2\n\n"
            "direction:\n"
            "- positive: an increase in metabolite concentration or activity is positively associated with the disease\n"
            "- negative: a decrease in metabolite concentration or activity is associated with the disease\n"
            "- neutral: the direction is unclear or the snippets do not contain enough information to decide\n\n"
            "key_finding: summarize in one sentence the core finding of this paper about the metabolite. Write it in English."
        )),
        HumanMessage(content=(
            f"Target metabolite: {keyword}\n\n"
            f"Full-text snippets:\n{combined}"
        )),
    ])

    return resp.model_dump()

class OutcomeMatch(BaseModel):
    is_match: bool
    reasoning: str
    mismatch_type: Literal[
        "broader_disease",
        "different_exposure",
        "correct_match",
        "partial_match"
    ]

class EvidenceSufficiency(BaseModel):
    needs_indirect_evidence: bool
    mismatch_type: str
    reasoning: str
    supplementary_pubmed_query: str = Field(
        default="",
        description=(
            "Additional PubMed query to fill evidence gap. "
            "Generate only if needs_indirect_evidence is True. "
            "Use Boolean logic, no double quotes."
        )
    )
    supplementary_openalex_keyword: str = Field(
        default="",
        description=(
            "Additional OpenAlex fulltext keyword to fill evidence gap. "
            "Generate only if needs_indirect_evidence is True and "
            "mismatch_type is broader_disease or all_neutral. "
            "3-5 words separated by spaces."
        )
    )
    search_source: Literal["pubmed", "openalex", "both", "none"] = Field(
        description=(
            "Which database to use for supplementary search. "
            "- none: correct_match, no need to search. "
            "- pubmed: different_exposure, abstract-level search is enough. "
            "- openalex: broader_disease or all_neutral, need full-text search. "
            "- both: partial_match, expand search on both sides."
        )
    )

@tool
def check_evidence_sufficiency(
    extracted_papers: list[dict],
    question: str,
    need_fulltext: bool = False  # 💡 1. pass in the need_fulltext constraint
) -> dict:
    """Use the LLM and the traits of the retrieved literature to decide whether more searching is needed"""
    total = len(extracted_papers)
    directions = [p.get("direction") for p in extracted_papers]
    all_neutral = all(d == "neutral" for d in directions)

    papers_summary = json.dumps(
        [
            {
                "title": p.get("title", ""),
                "population": p.get("population", ""),
                "exposure": p.get("exposure", ""),
                "outcome": p.get("outcome", ""),
                "key_finding": p.get("key_finding", ""),
                "direction": p.get("direction", ""),
            }
            for p in extracted_papers
        ],
        ensure_ascii=False,
    )

    structured_llm = llm.with_structured_output(EvidenceSufficiency)

    # 💡 2. Inject the OpenAlex constraint into the prompt dynamically
    openalex_constraint = ""
    if not need_fulltext:
        openalex_constraint = (
            "\nCRITICAL LIMITATION:\n"
            "The current system environment has 'need_fulltext=False'. "
            "DO NOT choose 'openalex' or 'both' for search_source. DO NOT generate supplementary_openalex_keyword. "
            "If broader_disease or all_neutral occurs, you MUST fallback to use 'pubmed' for search_source and generate a highly specific pubmed_query instead!"
        )

    resp = structured_llm.invoke([
        SystemMessage(content=(
            "You are a biomedical evidence evaluator. "
            "Given a research question and extracted paper summaries, "
            "evaluate whether the evidence is sufficient and generate supplementary search strategies if needed.\n\n"

            "Step 1 - Classify mismatch:\n"
            "- correct_match: papers study exactly the same exposure AND outcome.\n"
            "- partial_match: papers match exposure OR outcome but not both exactly.\n"
            "- broader_disease: outcome in papers is broader than the question.\n"
            "  Example: question=oral cancer, papers=head and neck cancer.\n"
            "- different_exposure: exposure in papers differs from the question.\n"
            "  Example: question=citric acid, papers=other TCA metabolites.\n\n"

            "Step 2 - Decide if supplementary search is needed:\n"
            "- correct_match AND directions are not all neutral → needs_indirect_evidence=False\n"
            "- anything else → needs_indirect_evidence=True\n\n"

            "Step 3 - Generate supplementary queries if needed:\n"
            "- broader_disease or all_neutral → use openalex fulltext search\n"
            "  Generate openalex keyword targeting the specific compound + narrower disease\n"
            "- different_exposure → use pubmed\n"
            "  Generate pubmed query with corrected exposure terms\n"
            "- partial_match → use both\n"
            "  Generate both pubmed and openalex queries\n"
            f"{openalex_constraint}"  # 💡 inject the constraint
        )),
        HumanMessage(content=(
            f"Research question: {question}\n"
            f"System context - need_fulltext: {need_fulltext}\n"  # 💡 let the LLM see it
            f"All neutral directions: {all_neutral}\n"
            f"Total papers found: {total}\n\n"
            f"Extracted paper summaries:\n{papers_summary}"
        )),
    ])

    return {
        "needs_indirect_evidence":       resp.needs_indirect_evidence,
        "mismatch_type":                 resp.mismatch_type,
        "reasoning":                     resp.reasoning,
        "supplementary_pubmed_query":     resp.supplementary_pubmed_query,
        "supplementary_openalex_keyword": resp.supplementary_openalex_keyword,
        "search_source":                 resp.search_source,
        "direct_paper_count":            total,
        "all_neutral":                   all_neutral,
    }