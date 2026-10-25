"use client";

import { useT } from "@/src/i18n/LocaleContext";

type ExternalId = { id?: string; url?: string };

type PugView = {
  cid?: number | string;
  molecular_formulas?: string[];
  molecular_weight?: string[];
  iupac_names?: string[];
  inchkeys?: string[];
  smiles?: string[];
  kegg?: ExternalId[];
  hmdb?: ExternalId[];
  chebi?: ExternalId[];
  drugbank?: ExternalId[];
};

export type IdMappingRow = {
  query?: string;
  pubchem_pug_view?: PugView | null;
};

const NA = "N/A";

function joinList(values?: string[]): string {
  return values && values.length ? values.join(", ") : NA;
}

function IdLinks({ items }: { items?: ExternalId[] }) {
  if (!items || items.length === 0) return <>{NA}</>;

  const seen = new Set<string>();
  const unique = items.filter((x) => {
    if (!x?.id || seen.has(x.id)) return false;
    seen.add(x.id);
    return true;
  });

  if (unique.length === 0) return <>{NA}</>;

  return (
    <>
      {unique.map((x, i) => (
        <span key={x.id}>
          {i > 0 && ", "}
          {x.url ? (
            <a href={x.url} target="_blank" rel="noopener noreferrer">
              {x.id}
            </a>
          ) : (
            x.id
          )}
        </span>
      ))}
    </>
  );
}

// The real id_mapping payload carries eleven identifier columns with outbound
// links (name, CID, Formula, MW, IUPAC, InChIKey, SMILES, KEGG, HMDB, ChEBI,
// DrugBank — see the PugView type above). The design's four-column
// mock (name / PubChem CID / KEGG / HMDB) is illustrative sample data;
// cutting this table to match it would drop information a physician
// explicitly asked for. Only the first column ("name") is a translated
// header — the rest are database/format abbreviations, not prose, so they
// stay identical across locales like the PubChem/KEGG/HMDB names elsewhere
// in this file.
const HEADERS = [
  "CID", "Formula", "MW", "IUPAC", "InChIKey",
  "SMILES", "KEGG", "HMDB", "ChEBI", "DrugBank",
];

/**
 * Renders the `id_mapping_result` payload as a real table.
 *
 * This replaces the backend's own raw object dump: the chat text for this
 * intent is built as `AIMessage(content=f"Search result:\n\n{data_list}")`
 * (backend/src/graph_agent/graph/id_mapping_graph.py:105), which f-string-
 * interpolates the raw `data_list` list of dicts — Python's default
 * str()/repr() of the object — straight into the reply. This component reads
 * the same structured data and shows it as a table instead of that dump.
 */
export default function IdMappingTable({ rows }: { rows: IdMappingRow[] }) {
  const { t } = useT();
  if (!rows || rows.length === 0) return null;

  return (
    // The eleven-column table overflows at narrow widths (e.g. the 380px
    // result-panel floor). Scrolling sideways inside its own box keeps it
    // legible instead of squeezing the conversation column — the same
    // convention AnalysisHighlights' R-code block and ArtifactGallery's
    // table use.
    <div className="overflow-x-auto">
      <table className="table" style={{ fontVariantNumeric: "tabular-nums" }}>
        <thead>
          <tr>
            <th className="whitespace-nowrap">{t("result.colName")}</th>
            {HEADERS.map((h) => (
              <th key={h} className="whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const view =
              row.pubchem_pug_view && typeof row.pubchem_pug_view === "object"
                ? row.pubchem_pug_view
                : {};
            const cid = view.cid ?? NA;

            return (
              <tr key={`${row.query}-${idx}`} className="align-top">
                <td>{row.query ?? "Unknown"}</td>
                <td>
                  {cid !== NA ? (
                    <a
                      href={`https://pubchem.ncbi.nlm.nih.gov/compound/${cid}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {cid}
                    </a>
                  ) : (
                    NA
                  )}
                </td>
                <td>{joinList(view.molecular_formulas)}</td>
                <td>{joinList(view.molecular_weight)}</td>
                <td className="max-w-[16rem] break-words">{joinList(view.iupac_names)}</td>
                <td className="font-mono break-all">{joinList(view.inchkeys)}</td>
                <td className="max-w-[14rem] font-mono break-all">{joinList(view.smiles)}</td>
                <td><IdLinks items={view.kegg} /></td>
                <td><IdLinks items={view.hmdb} /></td>
                <td><IdLinks items={view.chebi} /></td>
                <td><IdLinks items={view.drugbank} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
