import requests
from langchain.tools import tool
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_id_with_url(sec):
    items = []
    # Iterate over all Information items under this Section
    for info in sec.get("Information", []):
        # 1. Grab the ID string
        swm = info.get("Value", {}).get("StringWithMarkup", [])
        if swm:
            id_value = swm[0].get("String")
            
            # 2. Grab the URL (at the same level as Value)
            # Use .get() so an item without a URL does not raise
            url_value = info.get("URL") 
            
            items.append({
                "id": id_value,
                "url": url_value
            })
    return items

def deduplicate_dict_list(lst):
    seen = set()
    new_list = []
    for d in lst:
        key = (d.get("id"), d.get("url"))  # tuples are hashable
        if key not in seen:
            seen.add(key)
            new_list.append(d)
    return new_list

def get_session():
    session = requests.Session()
    # Define the retry policy
    retry_strategy = Retry(
        total=3,                # Total number of retries
        backoff_factor=1,       # Backoff factor (intervals of 1s, 2s, 4s...)
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    return session

# {
#     "cid": 2519,
#     "iupac_names": ["1,3,7-trimethylpurine-2,6-dione"],
#     "inchikeys": ["RYYVLZVUVIJVGH-UHFFFAOYSA-N"],
#     "smiles": ["Cn1cnc2c1c(=O)n(C)c(=O)n2C"],
#     "molecular_formulas": ["C8H10N4O2"],
#     "chebi": ["CHEBI:27732"],
#     "drugbank": ["DB00201"],
#     "hmdb": ["HMDB0001847"],
#     "kegg": [
#         {
#             "id": "C07481",
#             "url": "https://www.kegg.jp/dbget-bin/www_bget?cpd:C07481"
#         }
#     ]
# }

def pubchem_query(cid):
    PUG_VIEW_URL = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    
    # Initialise everything as lists so no data is lost
    result = {
        "cid": cid,
        "iupac_names": [],
        "inchikeys": [],
        "smiles": [],
        "molecular_formulas": [],
        "molecular_weight": [],
        "chebi": [],
        "drugbank": [],
        "hmdb": [],
        "kegg": []
    }
    session = get_session()

    try:
        res = session.get(PUG_VIEW_URL, timeout=10)
        res.raise_for_status()
        data = res.json()

        sections = data.get("Record", {}).get("Section", [])
        main_sec = next((s for s in sections if s.get("TOCHeading") == "Names and Identifiers"), {})
        sub_sections = main_sec.get("Section", [])

        main_sec_b = next((s for s in sections if s.get("TOCHeading") == "Chemical and Physical Properties"), {})
        sub_sections_b = main_sec_b.get("Section", [])

        # --- Optimised extraction function: returns a list ---
        def extract_all_vals(sec):
            vals = []
            for info in sec.get("Information", []):
                swm = info.get("Value", {}).get("StringWithMarkup", [])
                if swm:
                    vals.append(swm[0].get("String"))
            return vals

        for sub in sub_sections:
            heading = sub.get("TOCHeading")

            # 1. Molecular formula
            if heading == "Molecular Formula":
                result["molecular_formulas"].extend(extract_all_vals(sub))

            # 2. Computed descriptors
            elif heading == "Computed Descriptors":
                for d in sub.get("Section", []):
                    d_h = d.get("TOCHeading")
                    if d_h == "IUPAC Name":
                        result["iupac_names"].extend(extract_all_vals(d))
                    elif d_h == "InChIKey":
                        result["inchikeys"].extend(extract_all_vals(d))
                    elif d_h == "SMILES":
                        result["smiles"].extend(extract_all_vals(d))

            # 3. Identifiers
            elif heading == "Other Identifiers":
                # Map TOCHeading to the result key you want
                target_map = {
                    "KEGG ID": "kegg",
                    "ChEBI ID": "chebi",
                    "DrugBank ID": "drugbank",
                    "HMDB ID": "hmdb"
                }
                for i in sub.get("Section", []):
                    i_h = i.get("TOCHeading")
                    if i_h in target_map:
                        target_key = target_map[i_h]
                        # Put the list of ID + URL straight into the matching key
                        result[target_key].extend(get_id_with_url(i))

        for sub in sub_sections_b:
            heading = sub.get("TOCHeading")
            # 1. Molecular formula
            if heading == "Computed Properties":
                for d in sub.get("Section", []):
                    d_h = d.get("TOCHeading")
                    if d_h == "Molecular Weight":
                        result["molecular_weight"].extend(extract_all_vals(d))

        # Deduplicate (optional): different data sources sometimes provide duplicate strings
        for key in result:
            if isinstance(result[key], list) and result[key]:
                if isinstance(result[key][0], dict):
                    result[key] = deduplicate_dict_list(result[key])
                else:
                    result[key] = list(set(result[key]))
        return result

    except Exception as e:
        print(f"Error CID {cid}: {e}")
        return result
# Test call
# result = pubchem_fast_query(1032)
# print(f"ID: {result['kegg_id']}, Link: {result['url']}")



@tool
def pubchem_id_mapping(metabolite_names: list[str]):
    """
    Starting with the name, PUG VIEW provides detailed information on a specific metabolite. It's used when a user wants to search for detailed information about a particular metabolite.
    """
    # 1. Initialise
    NAME_TO_CID_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/json"
    
    results = []
    queries = [n.strip() for n in metabolite_names.split(",")] if isinstance(metabolite_names, str) else metabolite_names
    session = get_session()
    for q in queries:
        item = {"query": q, "cid": "Not Found", "pubchem_pug_view": "Not Found"}
        
        try:
            # 2. Step one: Name -> CID (PUG REST)
            res_cid = session.get(NAME_TO_CID_URL.format(name=q), timeout=10)
            if res_cid.status_code == 200:
                cid = res_cid.json().get("IdentifierList", {}).get("CID", [None])[0]
                
                if cid:
                    item["cid"] = cid
                    
                    # 3. Step two: CID -> Full Details (PUG VIEW)
                    pubchem_fast_query = pubchem_query(cid)
                    item["pubchem_pug_view"] = pubchem_fast_query

            results.append(item)
            
            # PubChem PUG VIEW returns a lot of data; adding a little delay is advisable
            time.sleep(0.3)
            
        except Exception as e:
            print(f"Error processing {q}: {e}")
            item["cid"] = "Error"
            results.append(item)

    return results


# result=pubchem_id_mapping("L-Glutamine")
# print(result)

#     DEFAULT_METABOLITES = [
#         "glucose", "lactate", "pyruvate", "alanine", "glutamine",
#         "glutamate", "citrate", "succinate", "fumarate", "malate",
#         "alpha-ketoglutarate", "oxaloacetate", "acetyl-CoA",
#         "palmitic acid", "stearic acid", "oleic acid", "linoleic acid",
#         "cholesterol", "sphingomyelin", "phosphatidylcholine",
#         "tryptophan", "tyrosine", "phenylalanine", "leucine", "isoleucine",
#         "valine", "serine", "threonine", "methionine", "cysteine",
#         "lysine", "arginine", "histidine", "proline", "glycine",
#         "aspartate", "asparagine", "urea", "uric acid", "creatinine",
#         "choline", "betaine", "trimethylamine N-oxide", "butyrate",
#         "propionate", "acetate", "indole", "kynurenine", "serotonin",
#         "dopamine", "GABA", "adenosine", "inosine", "hypoxanthine",
#     ]
