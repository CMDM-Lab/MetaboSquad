import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import IdMappingTable from "../IdMappingTable";

const rows = [
  {
    query: "citric acid",
    pubchem_pug_view: {
      cid: 311,
      molecular_formulas: ["C6H8O7"],
      molecular_weight: ["192.12"],
      iupac_names: ["2-hydroxypropane-1,2,3-tricarboxylic acid"],
      inchkeys: ["KRKNYBCHXYNGOX-UHFFFAOYSA-N"],
      smiles: ["C(C(=O)O)C(CC(=O)O)(C(=O)O)O"],
      kegg: [{ id: "C00158", url: "https://www.kegg.jp/entry/C00158" }],
      hmdb: [{ id: "HMDB0000094", url: "https://hmdb.ca/metabolites/HMDB0000094" }],
      chebi: [],
      drugbank: [],
    },
  },
];

function renderTable(data: unknown[]) {
  return render(
    <LocaleProvider><IdMappingTable rows={data as never} /></LocaleProvider>,
  );
}

describe("IdMappingTable", () => {
  it("shows the metabolite name and CID", () => {
    renderTable(rows);
    expect(screen.getByText("citric acid")).toBeInTheDocument();
    expect(screen.getByText("311")).toBeInTheDocument();
  });

  it("the KEGG ID carries an outbound link that opens in a new window", () => {
    renderTable(rows);
    const link = screen.getByRole("link", { name: "C00158" });
    expect(link).toHaveAttribute("href", "https://www.kegg.jp/entry/C00158");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("the CID links to its PubChem page", () => {
    renderTable(rows);
    expect(screen.getByRole("link", { name: "311" })).toHaveAttribute(
      "href", "https://pubchem.ncbi.nlm.nih.gov/compound/311");
  });

  it("an empty list shows N/A rather than breaking the layout", () => {
    renderTable(rows);
    // chebi and drugbank are both empty arrays
    expect(screen.getAllByText("N/A").length).toBeGreaterThan(0);
  });

  it("does not blow up when pubchem_pug_view is not an object", () => {
    renderTable([{ query: "unknown", pubchem_pug_view: null }]);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("returns null for entirely empty data", () => {
    const { container } = renderTable([]);
    expect(container).toBeEmptyDOMElement();
  });

  // The real payload carries eleven identifier columns with outbound links.
  // The design's four-column mock (name / PubChem CID / KEGG / HMDB)
  // is illustrative sample data; cutting this table to match it would drop
  // information a physician explicitly asked for. This test is the guard
  // against a later "simplification" that trims the column set back down.
  it("keeps every identifier column the payload provides", () => {
    const fullRow = {
      query: "citric acid",
      pubchem_pug_view: {
        cid: 311,
        molecular_formulas: ["C6H8O7"],
        molecular_weight: ["192.12"],
        iupac_names: ["2-hydroxypropane-1,2,3-tricarboxylic acid"],
        inchkeys: ["KRKNYBCHXYNGOX-UHFFFAOYSA-N"],
        smiles: ["C(C(=O)O)C(CC(=O)O)(C(=O)O)O"],
        kegg: [{ id: "C00158", url: "https://www.kegg.jp/entry/C00158" }],
        hmdb: [{ id: "HMDB0000094", url: "https://hmdb.ca/metabolites/HMDB0000094" }],
        chebi: [{ id: "CHEBI:30769", url: "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:30769" }],
        drugbank: [{ id: "DB04272", url: "https://go.drugbank.com/drugs/DB04272" }],
      },
    };
    renderTable([fullRow]);
    for (const h of ["CID", "Formula", "KEGG", "HMDB", "ChEBI", "DrugBank"]) {
      expect(screen.getByRole("columnheader", { name: new RegExp(h, "i") })).toBeInTheDocument();
    }
  });
});
