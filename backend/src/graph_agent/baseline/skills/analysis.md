---
name: analysis
description: Use when user mentions "data analysis, peak table, CSV analysis, statistical analysis" AND provides a file path (but does not specify a full pipeline).
---

Workflow: 
1. Analyze the user's query and extract key study design metadata according to the provided schema
    group_name: The name of the experimental or study groups mentioned in the query.
    paired: Whether the study design is paired (e.g., before/after, matched samples).
    label_is_continuous: description="Whether the clinical outcome or label is a continuous variable (e.g., age, weight) rather than categorical.
    mode: The MS (Mass Spectrometry) ionization mode. Must be 'positive' or 'negative'. If not mentioned, return null."
2. Use `recommend_and_analysis`
3. Use `extract_significant`
4. If `mummichog_txt_path` is None, then `pubchem_id_mapping` is used; otherwise, `mummichog_analysis` is used.


