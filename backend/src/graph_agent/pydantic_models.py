from pydantic import BaseModel, Field
from typing import Literal

class SearchPubmed(BaseModel):
    pubmed_query: str = Field(
        description=(
            "A robust PubMed search query using Boolean logic (AND, OR). "
            "Combine synonyms within concepts using OR, and separate distinct concepts using AND. "
            "DO NOT use double quotes anywhere inside this string. "
            "Use MeSH terms if applicable."
        )
    )

class Metadata(BaseModel):
    group_name: str = Field(description="The name of the experimental or study groups mentioned in the query.")
    paired: bool = Field(description="Whether the study design is paired (e.g., before/after, matched samples).")
    label_is_continuous: bool = Field(description="Whether the clinical outcome or label is a continuous variable (e.g., age, weight) rather than categorical.")
    mode: Literal["positive", "negative"] | None = Field(
        default=None, 
        description="The MS (Mass Spectrometry) ionization mode. Must be 'positive' or 'negative'. If not mentioned, return null."
    )

class PaperDecision(BaseModel):
    idx: int
    decision: Literal["relevant", "irrelevant"]
    reason: str

class FilterResult(BaseModel):
    results: list[PaperDecision]

class PaperExtract(BaseModel):
    idx: int
    population: str
    exposure: str
    outcome: str
    study_design: str
    sample_size: str
    key_finding: str
    direction: Literal["positive", "negative", "neutral"]
    limitation: str

class ExtractResult(BaseModel):
    results: list[PaperExtract]

