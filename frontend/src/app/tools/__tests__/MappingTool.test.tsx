import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider, LOCALE_KEY } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import { en } from "@/src/i18n/messages/en";
import MappingTool from "../page";

describe("MappingTool", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function renderTool() {
    return render(
      <LocaleProvider>
        <MappingTool />
      </LocaleProvider>,
    );
  }

  it("calls /api/tool/mapping, not /tool/mapping", async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ url: "https://pubchem/...", data: { CID: 2244 } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", spy);

    renderTool();
    await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
    await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toContain("/api/tool/mapping");
    expect(spy.mock.calls[0][0]).not.toMatch(/[^i]\/tool\/mapping/);
  });

  // If the implementation only renders `data` and forgets `url` (or the
  // reverse), this test must go red — it asserts both appear on screen,
  // rather than a static "request succeeded" message that would stay green
  // either way.
  it("renders the backend's url and data, not a static success message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ url: "https://pubchem/x", data: { CID: 2244, MW: "180.16" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderTool();
    await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
    await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

    await waitFor(() => expect(screen.getByText(/180.16/)).toBeInTheDocument());
    expect(screen.getByText(/2244/)).toBeInTheDocument();
    expect(screen.getByText("https://pubchem/x")).toBeInTheDocument();
    expect(screen.queryByText("請求成功")).not.toBeInTheDocument();
  });

  it("shows an error card when the backend errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "PubChem 錯誤: 找不到" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderTool();
    await userEvent.type(screen.getByPlaceholderText(/2244/), "999999999");
    await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText(/PubChem 錯誤/)).toBeInTheDocument();
  });

  // A dropped connection makes fetch throw a TypeError (also an instance of
  // Error). Implementing this as `e instanceof Error ? e.message : ...`
  // would print that raw English string at a physician instead of the
  // localised network message.
  it("shows the localised network-error message when fetch throws, not the raw English text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    renderTool();
    await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
    await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

    await waitFor(() =>
      expect(screen.getByText("無法連線到伺服器，請確認網路後重試")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });

  it("does not submit when identifier is empty", async () => {
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);

    renderTool();
    await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

    expect(spy).not.toHaveBeenCalled();
  });

  describe("clinical redesign", () => {
    // /api/tool/mapping is a thin PubChem PUG-REST
    // proxy — there is no KEGG/HMDB/ChEBI lookup outside the agent path.
    // Rendering toggle buttons for those databases would promise a lookup
    // this page cannot perform.
    it("offers only the databases the endpoint can actually query", () => {
      renderTool();
      expect(screen.queryByRole("button", { name: /KEGG|HMDB|ChEBI/ })).toBeNull();
    });

    it("aligns the result column with the identifier field, not its label", () => {
      renderTool();
      expect(screen.getByTestId("tools-result-col")).toHaveStyle({ paddingTop: "24px" });
    });

    it("renders English at locale=en", async () => {
      localStorage.setItem(LOCALE_KEY, "en");
      try {
        renderTool();
        await waitFor(() =>
          expect(screen.getByText(en["tools.title"]!)).toBeInTheDocument());
      } finally {
        localStorage.removeItem(LOCALE_KEY);
      }
    });
  });

  // Namespace/Identifier/Operation/Output
  // Format/Properties are ordinary translatable nouns, not API jargon (unlike
  // the CID/SMILES/InChI option *values* they sit above), so they now go
  // through their own tools.*Label i18n keys instead of a raw English
  // literal.
  describe("field labels are translated", () => {
    it("uses the Chinese functional labels at the zh default, not the raw API term", () => {
      renderTool();
      expect(screen.getByText(zh["tools.namespaceLabel"])).toBeInTheDocument();
      expect(screen.getByText(zh["tools.identifierLabel"])).toBeInTheDocument();
      expect(screen.getByText(zh["tools.operationLabel"])).toBeInTheDocument();
      expect(screen.getByText(zh["tools.outputLabel"])).toBeInTheDocument();
      expect(screen.getByText(zh["tools.propertiesLabel"])).toBeInTheDocument();
    });

    it("uses the English API-facing terms at locale=en", async () => {
      localStorage.setItem(LOCALE_KEY, "en");
      try {
        renderTool();
        await waitFor(() => expect(screen.getByText(en["tools.title"]!)).toBeInTheDocument());
        expect(screen.getByText(en["tools.namespaceLabel"]!)).toBeInTheDocument();
        expect(screen.getByText(en["tools.identifierLabel"]!)).toBeInTheDocument();
        expect(screen.getByText(en["tools.operationLabel"]!)).toBeInTheDocument();
        expect(screen.getByText(en["tools.outputLabel"]!)).toBeInTheDocument();
        expect(screen.getByText(en["tools.propertiesLabel"]!)).toBeInTheDocument();
      } finally {
        localStorage.removeItem(LOCALE_KEY);
      }
    });
  });

  // A physician cannot act on a raw PubChem JSON
  // blob. The two JSON response shapes this form can actually produce
  // (operation=property and operation=synonyms, both output=json) must be
  // shaped into `.table` rows; everything else keeps the raw dump, visibly
  // marked as a fallback.
  describe("result shaping", () => {
    it("shapes a property/json response into table rows, not a raw JSON dump", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(
            JSON.stringify({
              url: "https://pubchem/property",
              data: {
                PropertyTable: {
                  Properties: [
                    { CID: 2244, MolecularFormula: "C9H8O4", MolecularWeight: "180.16" },
                  ],
                },
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      );

      renderTool();
      await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
      await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

      await waitFor(() => expect(screen.getByText("MolecularFormula")).toBeInTheDocument());
      expect(screen.getByText("C9H8O4")).toBeInTheDocument();
      expect(screen.getByText("MolecularWeight")).toBeInTheDocument();
      expect(screen.getByText("180.16")).toBeInTheDocument();
      // If this regressed to a raw dump, the JSON wrapper keys would appear
      // as plain text somewhere in the pre block.
      expect(screen.queryByText(/PropertyTable/)).not.toBeInTheDocument();
    });

    it("shapes a synonyms/json response into table rows, joining the Synonym array", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(
            JSON.stringify({
              url: "https://pubchem/synonyms",
              data: {
                InformationList: {
                  Information: [
                    { CID: 2244, Synonym: ["Aspirin", "Acetylsalicylic acid"] },
                  ],
                },
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      );

      renderTool();
      await userEvent.selectOptions(
        screen.getByLabelText(zh["tools.operationLabel"]),
        "synonyms",
      );
      await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
      await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

      await waitFor(() => expect(screen.getByText("Synonym")).toBeInTheDocument());
      expect(screen.getByText("Aspirin, Acetylsalicylic acid")).toBeInTheDocument();
      expect(screen.queryByText(/InformationList/)).not.toBeInTheDocument();
    });

    it("falls back to a visibly-marked raw dump for a shape it doesn't recognise", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(
            JSON.stringify({ url: "https://pubchem/csv", data: "CID,MolecularFormula\n2244,C9H8O4" }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      );

      renderTool();
      await userEvent.selectOptions(screen.getByLabelText(zh["tools.outputLabel"]), "csv");
      await userEvent.type(screen.getByPlaceholderText(/2244/), "2244");
      await userEvent.click(screen.getByRole("button", { name: /查詢/ }));

      await waitFor(() =>
        expect(screen.getByText("Raw response (unparsed)")).toBeInTheDocument());
      expect(screen.getByText(/CID,MolecularFormula/)).toBeInTheDocument();
    });
  });
});
