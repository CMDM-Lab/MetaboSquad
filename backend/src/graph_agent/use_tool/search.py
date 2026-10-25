from Bio import Entrez
from langchain.tools import tool
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import arxiv
import time
from dotenv import load_dotenv
import requests
load_dotenv()

Entrez.email = os.getenv('EMAIL')
Entrez.api_key = os.getenv('NCBI_KEY')
REQUEST_DELAY = 0.1 if Entrez.api_key else 0.35

@tool
def search_pubmed(query: str) -> list[dict]:
    """Query Pubmed for ALL matching papers (Titles/Metadata only) without limits."""
    try:
        print(f"Starting total search for PubMed: {query}")


        handle = Entrez.esearch(db="pubmed", term=query, retmax=0, sort="relevance")
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
                        sort="relevance"
                    )
                    result = Entrez.read(handle)
                    all_ids.extend(result.get("IdList", []))
                    handle.close()
                    break
                except Exception as e:
                    if attempt == 2: raise e
                    time.sleep(2)

        print(f"Successfully retrieved all {len(all_ids)} PMIDs. Fetching metadata now...")

        # 3. Step three: call esummary in batches to get titles (important! at most 300 IDs per call to keep the URL from getting too long)
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
                        retmode="xml"
                    )
                    records = Entrez.read(handle)
                    handle.close()
                    
                    # Parse this batch's summary metadata
                    for record in records:
                        try:
                            pmid = str(record['Id'])
                            title = record.get('Title', 'N/A')
                            
                            authors_list = record.get('AuthorList', [])
                            authors = ", ".join(authors_list[:3]) if authors_list else "N/A"
                            if len(authors_list) > 3:
                                authors += " et al."

                            pub_date = record.get('PubDate', 'N/A')
                            year = pub_date.split(' ')[0] if pub_date != 'N/A' else 'N/A'

                            doi =  record.get('DOI', 'N/A')

                            results.append({
                                "title": title,
                                "authors": authors,
                                "journal": record.get('Source', 'N/A'),
                                "year": year,
                                "doi": doi,
                                "pmid": pmid,
                                "abstract": "N/A",  # Still left empty; fetched after title_filter
                                "source": "pubmed",
                                "pm_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                            })
                        except Exception as inner_e:
                            continue
                    break  # Success, exit the retry loop
                except Exception as e:
                    if attempt == 2: 
                        print(f"Failed to fetch summary batch starting at {i}: {e}")
                    time.sleep(2)

        print(f"Finished. Total metadata dictionaries compiled: {len(results)}")
        return results

    except Exception as e:
        print(f"Critical error in full PubMed search: {e}")
        return []

@tool
def search_abstract(all_ids: list[str]) -> list[dict]:
    """Query Pubmed for abstracts of specific PMIDs in batches."""
    if not all_ids:
        return []
        
    results = []
    
    # Precautionary batching: fetch abstracts for only 50 papers at a time, rock solid
    batch_size = 50
    for chunk_start in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[chunk_start:chunk_start+batch_size]
        
        for attempt in range(3): # Add a retry mechanism
            try:
                handle = Entrez.efetch(
                    db="pubmed",
                    id=batch_ids,
                    rettype="abstract",
                    retmode="xml"
                )
                records = Entrez.read(handle)
                handle.close()
                
                for record in records.get('PubmedArticle', []):
                    pmid = str(record['MedlineCitation']['PMID'])
                    article = record['MedlineCitation']['Article']
                    abstract = "N/A"
                    if 'Abstract' in article and 'AbstractText' in article['Abstract']:
                        abstract_texts = article['Abstract']['AbstractText']
                        if isinstance(abstract_texts, list):
                            abstract = " ".join([str(text) for text in abstract_texts])
                        else:
                            abstract = str(abstract_texts)
                    
                    results.append({"pmid": pmid, "abstract": abstract})
                break
            except Exception as e:
                if attempt == 2: print(f"Failed fetching abstracts: {e}")
                time.sleep(2)
                
    return results

