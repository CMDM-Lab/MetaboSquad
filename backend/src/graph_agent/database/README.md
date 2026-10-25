# Datasets used for pathway analysis

The pathway gene-set (GMT) files are **not** distributed with this repository.
KEGG and SMPDB data are subject to their providers' terms of use, so each user
generates them locally. Both files are listed in `.gitignore`.

## File structure
```
backend/src/graph_agent/database
├── README.md
├── kegg_metabolites_hsa.gmt     # KEGG, generate with the command below
└── smpdb_metabolites.gmt        # SMPDB, optional (the file is about 163,109 KB)
```

GMT format: one pathway per line, `pathway name<TAB>pathway ID<TAB>C00001<TAB>...`.

## Generating the KEGG file

From `backend/`:

```bash
venv/bin/python -m src.graph_agent.use_tool.download_path_db
```

This calls `download_kegg_metabolite_gmt()` in `use_tool/download_path_db.py`.
It queries the KEGG REST API (about 370 requests, a few minutes), paces the
requests, and retries refusals. If any pathway still cannot be fetched, it
exits with an error and writes no file, so a partial download can never be
used by accident.

Use of the KEGG REST API is subject to the
[KEGG terms](https://www.kegg.jp/kegg/legal.html).

## Version used in the manuscript

KEGG is updated continuously, so a newly generated file can differ from the one
used for the published results, and pathway enrichment p-values and rankings
can change with it.

| | Manuscript version |
| :--- | :--- |
| Download date | 2026-06-03 |
| Organism | `hsa` |
| Pathways | 304 |
| Pathway–compound links | 10,593 |
| SHA-256 | `ea30de9a977049bf3b419ad4f101af26d2b40203be29bce6c248126d3e73e592` |

Check your file with `sha256sum kegg_metabolites_hsa.gmt`. For comparison, a
file generated on 2026-10-25 had 305 pathways and 10,667 links: one pathway was
added (`hsa04156`) and the compound lists of 9 pathways changed. To reproduce
the published results exactly, contact the authors for the 2026-06-03 file.

## Generating the SMPDB file

`download_smpdb_metabolite_gmt()` in the same module downloads and converts
SMPDB.
