"use client";

import { useState } from "react";
import MultiSelectDropdown from "./components/MultiSelectDropdown";
import { apiJson, ApiError } from "@/src/lib/apiClient";
import { useT } from "@/src/i18n/LocaleContext";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import Hairline from "@/src/components/Hairline";

// The option *values* below (CID/Name/SMILES/InChI, Property/Synonyms,
// JSON/CSV/XML, and the property ids in PROPERTY_OPTIONS) are PubChem
// PUG-REST enum literals this form maps directly onto (backend/api/routers/
// tool.py's MappingID: namespace, identifier, operation, property, output).
// Like IdMappingTable.tsx's HEADERS (src/modules/results/IdMappingTable.tsx:
// 71-74), these are API parameter values and database/format abbreviations,
// not prose, so they stay identical across locales without needing an i18n
// key. The field *labels* above each control are ordinary translatable
// nouns, not API jargon, so those go through tools.namespaceLabel /
// identifierLabel / operationLabel / outputLabel / propertiesLabel instead
// (otherwise a Chinese-reading physician meets untranslated English on every
// field).
const NAMESPACE_OPTIONS = [
  { value: "cid", label: "CID" },
  { value: "name", label: "Name" },
  { value: "smiles", label: "SMILES" },
  { value: "inchi", label: "InChI" },
];

const OPERATION_OPTIONS = [
  { value: "property", label: "Property" },
  { value: "synonyms", label: "Synonyms" },
];

const OUTPUT_OPTIONS = ["JSON", "CSV", "XML"];

const PROPERTY_OPTIONS = [
  { id: "MolecularFormula", label: "MolecularFormula" },
  { id: "MolecularWeight", label: "MolecularWeight" },
  { id: "IUPACName", label: "IUPACName" },
  { id: "SMILES", label: "SMILES" },
  { id: "InChI", label: "InChI" },
  { id: "InChIKey", label: "InChIKey" },
  { id: "XLogP", label: "XLogP" },
  { id: "ExactMass", label: "ExactMass" },
  { id: "TPSA", label: "TPSA" },
  { id: "Complexity", label: "Complexity" },
  { id: "Charge", label: "Charge" },
  { id: "HBondDonorCount", label: "HBondDonorCount" },
  { id: "HBondAcceptorCount", label: "HBondAcceptorCount" },
  { id: "AnnotationTypes", label: "AnnotationTypes" },
];

type ToolResult = { url: string; data: unknown; operation: string; output: string };

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Raw JSON is not dumped for every path: the two JSON paths this form can
// actually produce have a known, flat shape:
//   - operation=property, output=json -> data.PropertyTable.Properties[0]
//     is an object with exactly the properties the user selected (e.g.
//     { CID: 2244, MolecularFormula: "C9H8O4", MolecularWeight: "180.16" }).
//   - operation=synonyms, output=json -> data.InformationList.Information[0]
//     is an object such as { CID: 2244, Synonym: ["aspirin", ...] }.
// Both shape cleanly into key/value `.table` rows. Anything else — CSV or
// XML output, or a response that doesn't match the shape above — has no
// such guarantee, so it falls back to the raw dump rather than risk silently
// mis-rendering a shape this function guessed wrong about.
function extractFlatRecord(
  operation: string,
  output: string,
  data: unknown,
): Record<string, unknown> | null {
  if (output !== "json" || !isPlainRecord(data)) return null;

  if (operation === "property") {
    const propertyTable = data.PropertyTable;
    const properties = isPlainRecord(propertyTable) ? propertyTable.Properties : undefined;
    if (Array.isArray(properties) && properties.length > 0 && isPlainRecord(properties[0])) {
      return properties[0];
    }
    return null;
  }

  if (operation === "synonyms") {
    const informationList = data.InformationList;
    const information = isPlainRecord(informationList) ? informationList.Information : undefined;
    if (Array.isArray(information) && information.length > 0 && isPlainRecord(information[0])) {
      return information[0];
    }
    return null;
  }

  return null;
}

function formatCellValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function MappingTool() {
  const { t } = useT();
  const [selectedNamespace, setSelectedNamespace] = useState("cid");
  const [selectedIdentifier, setSelectedIdentifier] = useState("");
  const [selectedOperation, setSelectedOperation] = useState("property");
  const [selectedProperties, setSelectedProperties] = useState<string[]>([]);
  const [selectedOutput, setSelectedOutput] = useState("json");
  const [result, setResult] = useState<ToolResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const handleSubmit = async () => {
    if (!selectedIdentifier.trim()) return;

    setPending(true);
    setError(null);
    setResult(null);

    try {
      const data = await apiJson<{ url: string; data: unknown }>("/api/tool/mapping", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          namespace: selectedNamespace,
          identifier: selectedIdentifier,
          operation: selectedOperation,
          ...(selectedOperation === "property" && {
            property: selectedProperties,
          }),
          output: selectedOutput,
        }),
      });
      // The operation/output that produced this response are captured
      // alongside it (rather than read back from the live form state at
      // render time), so a user changing Operation/Output after a result
      // comes back can never make extractFlatRecord shape the *new*
      // selection's expectations onto the *old* response.
      setResult({ ...data, operation: selectedOperation, output: selectedOutput });
    } catch (e) {
      // ApiError.detail is already-localised backend text and is safe to show
      // verbatim. Everything else — including the dropped-connection
      // TypeError fetch throws, which is also an instance of Error — falls
      // back to the translated network message, so a physician never sees an
      // untranslated English technical string.
      setError(e instanceof ApiError ? e.detail : t("error.network"));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1040px] px-[var(--space-6)] py-[var(--space-8)]">
      <Kicker size="md">{t("tools.kicker")}</Kicker>
      <h2 className="my-[var(--space-2)]">{t("tools.title")}</h2>
      <p className="max-w-[64ch] text-justify text-[13.5px] hyphens-auto text-[color-mix(in_srgb,var(--color-text)_74%,transparent)]">
        {t("tools.lede")}
      </p>
      <Hairline />

      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] items-start gap-[var(--space-6)]">
        <div className="flex flex-col gap-[var(--space-4)]">
          <div className="field">
            <label htmlFor="tools-namespace">{t("tools.namespaceLabel")}</label>
            <select
              id="tools-namespace"
              className="input"
              value={selectedNamespace}
              onChange={(e) => setSelectedNamespace(e.target.value)}
            >
              {NAMESPACE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="tools-identifier">{t("tools.identifierLabel")}</label>
            <input
              id="tools-identifier"
              className="input"
              placeholder="e.g. 2244"
              value={selectedIdentifier}
              onChange={(e) => setSelectedIdentifier(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="tools-operation">{t("tools.operationLabel")}</label>
            <select
              id="tools-operation"
              className="input"
              value={selectedOperation}
              onChange={(e) => setSelectedOperation(e.target.value)}
            >
              {OPERATION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="tools-output">{t("tools.outputLabel")}</label>
            <select
              id="tools-output"
              className="input"
              value={selectedOutput}
              onChange={(e) => setSelectedOutput(e.target.value)}
            >
              {OUTPUT_OPTIONS.map((o) => (
                <option key={o} value={o.toLowerCase()}>{o}</option>
              ))}
            </select>
          </div>

          {selectedOperation === "property" && (
            <div className="field">
              <label id="tools-properties-label">{t("tools.propertiesLabel")}</label>
              <MultiSelectDropdown
                options={PROPERTY_OPTIONS}
                value={selectedProperties}
                onChange={setSelectedProperties}
              />
            </div>
          )}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={pending}
            className="btn btn-primary btn-block disabled:opacity-50"
          >
            {t("tools.run")}
          </button>
        </div>

        {/* POST /api/tool/mapping is a thin PubChem
            PUG-REST proxy — there is no KEGG/HMDB/ChEBI lookup outside the
            agent path. So this column renders only what the endpoint
            actually returned (the request URL and the raw response), never
            columns for databases this form cannot query. `padding-top: 24px`
            lines its first row up with the top of the textarea/input column
            rather than with that column's first label. */}
        <div data-testid="tools-result-col" style={{ paddingTop: "24px" }}>
          {error && <ErrorCard detail={error} />}
          {!error && result && (() => {
            const shaped = extractFlatRecord(result.operation, result.output, result.data);
            return (
              <table className="table" style={{ fontVariantNumeric: "tabular-nums" }}>
                <tbody>
                  <tr>
                    <th>Request URL</th>
                    <td className="break-all">
                      <a href={result.url} target="_blank" rel="noopener noreferrer">
                        {result.url}
                      </a>
                    </td>
                  </tr>
                  {shaped ? (
                    Object.entries(shaped).map(([key, value]) => (
                      <tr key={key}>
                        <th>{key}</th>
                        <td className="max-w-[20rem] break-words">{formatCellValue(value)}</td>
                      </tr>
                    ))
                  ) : (
                    // Fallback for anything extractFlatRecord doesn't recognise
                    // (CSV/XML output, or a JSON shape this form didn't
                    // anticipate) — visibly marked "unparsed" so it reads as a
                    // fallback, not as the page's normal, designed output.
                    <tr>
                      <th>Raw response (unparsed)</th>
                      <td>
                        <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all">
                          {typeof result.data === "string"
                            ? result.data
                            : JSON.stringify(result.data, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            );
          })()}
          {!error && !result && (
            <p className="border border-dashed border-divider p-[var(--space-4)] text-[13px] text-neutral-500">
              {t("tools.empty")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
