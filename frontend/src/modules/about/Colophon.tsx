"use client";

import { useT } from "@/src/i18n/LocaleContext";

// The five value strings below state what is true of this repo. There is
// deliberately no test-count row: a number like "95 backend · 113 frontend"
// rots the moment either suite gains or loses a test, and it goes stale
// silently. This component only renders the rows.
//
// Row labels (Frontend/Backend/Computation/Language model/Databases) are
// ordinary translatable nouns, not API jargon — unlike IdMappingTable.tsx's
// HEADERS, which are non-translatable database/format names (CID, KEGG,
// HMDB, ...). So these labels get their own i18n keys
// (about.colophon*Label) rather than being transliterated.
const ROWS = [
  { labelKey: "about.colophonFrontendLabel", valueKey: "about.colophonFrontend" },
  { labelKey: "about.colophonBackendLabel", valueKey: "about.colophonBackend" },
  { labelKey: "about.colophonComputationLabel", valueKey: "about.colophonComputation" },
  { labelKey: "about.colophonModelLabel", valueKey: "about.colophonModel" },
  { labelKey: "about.colophonDatabasesLabel", valueKey: "about.colophonDatabases" },
] as const;

export default function Colophon() {
  const { t } = useT();

  return (
    <table className="table" style={{ fontVariantNumeric: "tabular-nums" }}>
      <tbody>
        {ROWS.map((row) => (
          <tr key={row.valueKey}>
            <th className="w-[34%] align-top">{t(row.labelKey)}</th>
            <td>{t(row.valueKey)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
