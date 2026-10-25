# Agent source code in detail

## File structure
```
backend/src/graph_agent/
├── README.md
├── graph/                         # 4 subagents
├── pydantic_models.py             # Agent response schemas
├── state.py                       # AgentState definition
├── supervisor.py                  # supervisor agent (main graph)
├── tools.py                       # LLM-calling tools and document-writing tools
└── use_tool/                      # tools used by the agents
    ├── code.py                    # statistical analysis tool
    ├── download_path_db.py        # pathway-analysis database download tool
    ├── extract_significant.py     # extracts metabolites with FDR < 0.05
    ├── gemma_tool.py              # literature screening tool designed for gemma4:26b
    ├── literature_add.py          # literature screening tool
    ├── package_params.json        # downloaded database of all MetaboAnalystR functions and parameters (useful if you want to analyze directly in the Docker environment)
    ├── parameter_knoeledge.py     # predefined analysis scripts
    ├── pathway_analysis.py        # pathway analysis tool
    ├── plot_tool.py               # tool for measuring physical properties of figures
    ├── pubchem_id_mapping.py      # PubChem API client
    └── search.py                  # PubMed API client

```
