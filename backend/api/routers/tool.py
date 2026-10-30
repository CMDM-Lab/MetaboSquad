from typing import Optional
import httpx  
from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel

# Create a router
# prefix: path prefix for every route below
# tags: labels used to group routes in Swagger UI
# responses: shared error responses
router = APIRouter(
    prefix="/api/tool",
    tags=["tool"],
)

class MappingID(SQLModel):
    namespace: str
    identifier: str
    operation: str
    property: Optional[list[str]] = None
    output: str

@router.post("/mapping")
async def query_pubchem(request: MappingID):
    PUGREST_PROLOG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    
    # 1. Build the base part first
    url_parts = [
        PUGREST_PROLOG,
        "compound",
        request.namespace,
        request.identifier,
        request.operation
    ]
    
    # 2. If properties are given, join them into a string and append
    # e.g. ["CID", "SMILES"] -> "property/CID,SMILES"
    if request.property:
        properties_str = ",".join(request.property)
        url_parts.append(f"{properties_str}")
    
    # 3. Append the output format
    url_parts.append(request.output.lower())
    
    # 4. Join everything
    pugrest_url = "/".join(url_parts)

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(pugrest_url, timeout=10.0)
            
            res.raise_for_status()
            
            return {
                "url": pugrest_url,
                "data": res.json() if request.output.upper() == "JSON" else res.text.strip()
            }
            
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"PubChem error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")