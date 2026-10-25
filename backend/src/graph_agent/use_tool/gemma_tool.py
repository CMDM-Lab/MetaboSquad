import json
import os
import socket
import time
from typing import Literal

from Bio import Entrez
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

load_dotenv()


# ── 2. Pydantic Models ────────────────────────────────────────────────────────
class SearchPubmed(BaseModel):
    pubmed_query: str = Field(
        description="A robust PubMed search query using Boolean logic (AND, OR)."
    )


class PaperDecision(BaseModel):
    idx: int
    decision: Literal["relevant", "irrelevant"]
    reason: str = Field(description="One short phrase, max 8 words.")


class FilterResult(BaseModel):
    results: list[PaperDecision]


class PaperExtract(BaseModel):
    idx: int
    key_finding: str
    direction: Literal["positive", "negative", "neutral"]


class ExtractResult(BaseModel):
    results: list[PaperExtract]


# ── 3. LLM initialisation ─────────────────────────────────────────────────────
base_llm = ChatOllama(
    model="gemma4:26b",
    temperature=0.0,
    base_url="http://localhost:11434",
    num_ctx=8192,
    reasoning=False,
    format="json",
    keep_alive="30m",
    client_kwargs={"timeout": 120.0},
)


# ── 4. Helper functions ───────────────────────────────────────────────────────
def _generate_apa_marker(paper: dict) -> str:
    authors_str = paper.get("authors", "").strip()
    year = str(paper.get("year", "n.d.")).strip()

    if not authors_str or authors_str == "N/A":
        short_title = paper.get("title", "")[:20] + "..."
        return f"({short_title}, {year})"

    author_list = [a.strip() for a in authors_str.split(",") if a.strip()]

    if len(author_list) == 1:
        last_name = author_list[0].split(" ")[0]
        return f"({last_name}, {year})"
    elif len(author_list) == 2:
        last_name1 = author_list[0].split(" ")[0]
        last_name2 = author_list[1].split(" ")[0]
        return f"({last_name1} & {last_name2}, {year})"
    else:
        last_name1 = author_list[0].split(" ")[0]
        return f"({last_name1} et al., {year})"


def write_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"檔案已儲存至 {path}"


# ── 5. Gemma Tools ──────────────────────────────────────────────────────────
def query_expansion_gemma(question: str) -> SearchPubmed:
    system_prompt = (
        "You are a biomedical literature search specialist.\n"
        "Analyze the research question and generate a structured search query.\n\n"
        "Instructions:\n"
        "1. Identify key concepts (exposure, outcome, population).\n"
        "2. Combine synonyms using OR, and distinct concepts using AND.\n"
        "3. CRITICAL: Do NOT use double quotes inside the string.\n\n"
        "Output MUST be a JSON object with a 'pubmed_query' key:\n"
        '{"pubmed_query": "(concept1 OR synonym1) AND (concept2 OR synonym2)"}'
        "DO not use ```json"
    )

    expansion_llm = base_llm.bind(options={"num_predict":384})
    structured_llm = base_llm.with_structured_output(
        SearchPubmed
    )

    try:
        return structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ]
        )
    except Exception as e:
        print(f"⚠️ query_expansion 解析失敗，啟動備援: {e}")
        return SearchPubmed(pubmed_query=question)

import json, re
from langchain_core.messages import SystemMessage, HumanMessage

# def clean_json_string(text: str) -> str:
#     """Strip Markdown markers or preamble chatter that the LLM response may include"""
#     # Remove the ```json ... ``` wrapper
#     text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
#     text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
#     return text.strip()

def title_filter_tool_gemma(papers: list[dict], question: str) -> list[dict]:
    filter_llm = base_llm.bind(options={"num_predict":768})
    structured_llm = base_llm.with_structured_output(
        FilterResult
    )

    papers_json = json.dumps(
        [{"idx": i, "title": p["title"]} for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    system_prompt = (
        "You are a scientific literature screening assistant.\n"
        "Classify each paper based on whether its title is relevant to the research question.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "1. Respond ONLY with raw valid JSON. Do NOT use markdown code fences (no ```json).\n"
        "2. MUST contain a 'results' array matching this structure:\n"
        "{\n"
        '  "results": [\n'
        '    {"idx": 0, "decision": "irrelevant", "reason": "Short reason"}\n'
        "  ]\n"
        "}\n"
    )

    try:
        resp = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
            ]
        )
        rating_map = {r.idx: r for r in resp.results}
    except Exception as e:
        print(f"⚠️ title_filter LLM 輸出格式非標準 JSON，觸發降級相容機制: {e}")
        rating_map = {}

    for i, paper in enumerate(papers):
        rating = rating_map.get(i)
        if rating:
            paper["title_decision"] = rating.decision
            paper["reason"] = rating.reason
        else:
            paper["title_decision"] = "relevant"  # Fallback: keep everything
            paper["reason"] = "Parse error fallback"

    return sorted(papers, key=lambda x: 0 if x.get("title_decision") == "relevant" else 1)


def abstract_filter_tool_gemma(papers: list[dict], question: str) -> list[dict]:
    filter_llm = base_llm.bind(options={"num_predict":768})
    structured_llm = base_llm.with_structured_output(
        FilterResult
    )

    papers_json = json.dumps(
        [{"idx": i, "abstract": p["abstract"]} for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    system_prompt = (
        "You are a scientific literature screening assistant.\n"
        "Classify each paper based on whether its abstract is relevant to the research question.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "1. Respond ONLY with raw valid JSON. Do NOT use markdown code fences (no ```json).\n"
        "2. MUST contain a 'results' array matching this structure:\n"
        "{\n"
        '  "results": [\n'
        '    {"idx": 0, "decision": "irrelevant", "reason": "Short reason"}\n'
        "  ]\n"
        "}\n"
    )

    try:
        resp = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
            ]
        )
        rating_map = {r.idx: r for r in resp.results}
    except Exception as e:
        print(f"⚠️ abstract_filter 解析失敗，觸發降級相容機制: {e}")
        rating_map = {}

    for i, paper in enumerate(papers):
        rating = rating_map.get(i)
        if rating:
            paper["abstract_decision"] = rating.decision
            paper["reason"] = rating.reason
        else:
            paper["abstract_decision"] = "relevant"
            paper["reason"] = "Parse error fallback"

    return sorted(papers, key=lambda x: 0 if x.get("abstract_decision") == "relevant" else 1)


def abstract_extract_gemma(papers: list[dict], question: str) -> list[dict]:
    extract_llm = base_llm.bind(options={"num_predict":1500})
    structured_llm = base_llm.with_structured_output(
        ExtractResult
    )

    papers_json = json.dumps(
        [{"idx": i, "abstract": p["abstract"]} for i, p in enumerate(papers)],
        ensure_ascii=False,
    )

    system_prompt = (
        "You are a biomedical research extraction assistant.\n"
        "Extract core PECO elements from each abstract into structured JSON.\n\n"
        "CRITICAL INSTRUCTION:\n"
        "1. Respond ONLY with raw valid JSON. Do NOT use markdown code fences (no ```json).\n"
        "2. direction MUST be 'positive', 'negative', or 'neutral'."
        "3. MUST contain a 'results' array matching this structure:\n"
        "{\n"
        '  "results": [\n'
        '    {"idx": 0, "key_finding": "A case of ON developed in a patient with high antiphospholipid antibodies without corticosteroid therapy, suggesting a possible association between primary antiphospholipid syndrome", "direction": "positive"}\n'
        "  ]\n"
        "}\n"
    )

    try:
        resp = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Question: {question}\n\nPapers:\n{papers_json}"),
            ]
        )
        extract_map = {r.idx: r for r in resp.results}
    except Exception as e:
        print(f"⚠️ abstract_extract 解析失敗，觸發降級相容機制: {e}")
        extract_map = {}

    for i, paper in enumerate(papers):
        extract = extract_map.get(i)
        if extract:
            paper.update({
                "key_finding": extract.key_finding,
                "direction": extract.direction,
            })
        else:
            paper.update({
                "key_finding": paper.get("title", ""),
                "direction": "neutral"
            })

    return papers


def summary_tool_gemma(papers: list[dict], question: str) -> str:
    if not papers:
        return "_No relevant literature found for this viewpoint._"

    papers_json = json.dumps(
        [
            {
                "idx": i,
                "key_finding": p.get("key_finding", ""),
                "URL": p.get("pm_url", ""),
                "apa_marker": _generate_apa_marker(p),
            }
            for i, p in enumerate(papers)
        ],
        ensure_ascii=False,
    )

    summary_llm = base_llm.bind(options={"num_predict":2048})
    system_prompt = (
        "You are a metabolomics research assistant. Synthesize a summary to answer the question based strictly on key findings.\n"
        "Every single sentence must be cited using `[apa_marker](URL)` format. for example: [Kumar et al., 1998](https://pubmed.ncbi.nlm.nih.gov/9458032/)\n"
        "Do NOT fabricate or extrapolate.\n"
        "CRITICAL: Respond exclusively in English."
    )

    try:
        resp = base_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=f"Question: {question}\n\nPapers:\n{papers_json}"
                ),
            ]
        )
        return str(resp.content)
    except Exception as e:
        print(f"⚠️ summary_tool 執行失敗: {e}")
        return "_Summary generation failed due to a model error._"

Entrez.email = os.getenv('EMAIL')
Entrez.api_key = os.getenv('NCBI_KEY')
REQUEST_DELAY = 0.1 if Entrez.api_key else 0.35

# ── 6. PubMed API Search Functions ─────────────────────────────────────────
def search_pubmed_gemma(query: str) -> list[dict]:
    try:
        print(f"Starting total search for PubMed: {query}")

        handle = Entrez.esearch(
            db="pubmed", term=query, retmax=0, sort="relevance"
        )
        search_results = Entrez.read(handle)
        handle.close()

        total_count = int(search_results["Count"])
        print(f"Total papers found on PubMed: {total_count}")

        if total_count == 0:
            return []

        max_search_limit = min(total_count, 9998)
        all_ids = []

        for start in range(0, max_search_limit, 500):
            for attempt in range(3):
                try:
                    handle = Entrez.esearch(
                        db="pubmed",
                        term=query,
                        retstart=start,
                        retmax=500,
                        sort="relevance",
                    )
                    result = Entrez.read(handle)
                    all_ids.extend(result.get("IdList", []))
                    handle.close()
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    time.sleep(1)

        print(
            f"Successfully retrieved {len(all_ids)} PMIDs. Fetching metadata..."
        )

        results = []
        summary_batch_size = 300

        for i in range(0, len(all_ids), summary_batch_size):
            time.sleep(REQUEST_DELAY)
            batch_ids = all_ids[i : i + summary_batch_size]
            for attempt in range(3):
                try:
                    handle = Entrez.esummary(
                        db="pubmed",
                        id=",".join(batch_ids),
                        retmode="xml",
                    )
                    records = Entrez.read(handle)
                    handle.close()

                    for record in records:
                        try:
                            pmid = str(record["Id"])
                            title = record.get("Title", "N/A")
                            authors_list = record.get("AuthorList", [])
                            authors = (
                                ", ".join(authors_list[:3])
                                if authors_list
                                else "N/A"
                            )
                            if len(authors_list) > 3:
                                authors += " et al."

                            pub_date = record.get("PubDate", "N/A")
                            year = (
                                pub_date.split(" ")[0]
                                if pub_date != "N/A"
                                else "N/A"
                            )
                            doi = record.get("DOI", "N/A")

                            results.append(
                                {
                                    "title": title,
                                    "authors": authors,
                                    "journal": record.get("Source", "N/A"),
                                    "year": year,
                                    "doi": doi,
                                    "pmid": pmid,
                                    "abstract": "N/A",
                                    "source": "pubmed",
                                    "pm_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                }
                            )
                        except Exception:
                            continue
                    break
                except Exception as e:
                    if attempt == 2:
                        print(
                            f"Failed to fetch summary batch starting at {i}: {e}"
                        )
                    time.sleep(1)

        return results
    except Exception as e:
        print(f"Critical error in full PubMed search: {e}")
        return []


def search_abstract_gemma(all_ids: list[str]) -> list[dict]:
    if not all_ids:
        return []

    results = []
    batch_size = 50

    for chunk_start in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[chunk_start : chunk_start + batch_size]
        for attempt in range(3):
            try:
                handle = Entrez.efetch(
                    db="pubmed",
                    id=batch_ids,
                    rettype="abstract",
                    retmode="xml",
                )
                records = Entrez.read(handle)
                handle.close()

                for record in records.get("PubmedArticle", []):
                    pmid = str(record["MedlineCitation"]["PMID"])
                    article = record["MedlineCitation"]["Article"]
                    abstract = "N/A"
                    if (
                        "Abstract" in article
                        and "AbstractText" in article["Abstract"]
                    ):
                        abstract_texts = article["Abstract"]["AbstractText"]
                        if isinstance(abstract_texts, list):
                            abstract = " ".join(
                                [str(text) for text in abstract_texts]
                            )
                        else:
                            abstract = str(abstract_texts)

                    results.append({"pmid": pmid, "abstract": abstract})
                break
            except Exception as e:
                if attempt == 2:
                    print(f"Failed fetching abstracts: {e}")
                time.sleep(1)

    return results