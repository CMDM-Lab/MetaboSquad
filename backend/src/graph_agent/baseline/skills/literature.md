---
name: literature
description: Use when user wants to find background literature and generate report for a specific "scientific question", "field", or "multiple keywords"
---

Workflow: 
1. Generate pubmed_query:
    Identify the key biomedical concepts (exposure, outcome, population).
    For each concept, list synonyms and MeSH terms.
    Combine synonyms within a concept using OR.
    Combine distinct concepts using AND.
    CRITICAL: Do NOT use double quotes anywhere inside the pubmed_query string.
    "for example: (smoking OR tobacco OR cigarette) AND (oral cancer OR oral carcinoma OR OSCC),"
2. Use `search_pubmed`
3. If the title suggests the paper studies the relationship between the exposure and outcome in the research question. Use `write_file` write down the relevant literature metadata to `research/pure_res/temp_{date}.md")`
4. Use `search_abstract` input the Pubmed ID and search the paper pass filter
5. If the abstaract also suggests the paper studies the relationship between the exposure and outcome in the research question. Use `edit_file` write down the relevant literature metadata to `research/pure_res/temp_{date}.md")`
6. Extract high-quality structured information from a peer-reviewed abstract that has already been verified as highly relevant to the research question.
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
7. Use `edit_file` write down the additional metadata to `research/pure_res/temp_{date}.md")`
8. Synthesize a summary to answer the user's question based strictly on the provided literature key findings.
        - The direction of positive, negative, and neutral need to be summarized separately.
        - Every single sentence in your response must be cited.
        - At the end of each sentence, append its corresponding `[apa_marker]` formatted as a clickable markdown hyperlink pointing to its specific URL. (Format: [apa_marker](url)).
        - Do NOT fabricate, extrapolate, or guess any information. Base your response 100 percent on the provided key finding.
9. Use `write_file` write down the summary answer report to `research/pure_res/result_{date}.md")`


