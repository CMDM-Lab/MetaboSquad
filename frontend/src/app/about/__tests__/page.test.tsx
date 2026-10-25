import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider, LOCALE_KEY } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import { en } from "@/src/i18n/messages/en";
import AboutPage from "../page";

function renderAbout() {
  return render(
    <LocaleProvider>
      <AboutPage />
    </LocaleProvider>,
  );
}

describe("AboutPage", () => {
  it("renders English at locale=en", async () => {
    localStorage.setItem(LOCALE_KEY, "en");
    try {
      renderAbout();
      await waitFor(() =>
        expect(screen.getByText(en["about.title"]!)).toBeInTheDocument());
    } finally {
      localStorage.removeItem(LOCALE_KEY);
    }
  });

  // The body's three paragraphs must actually flow as two CSS columns, not
  // just visually resemble it — a single-column layout with the same text
  // would pass any assertion that only checks the paragraphs are present.
  it("lays the body paragraphs out as a two-column flow", () => {
    renderAbout();
    expect(screen.getByTestId("about-columns")).toHaveStyle({ columns: "2" });
  });

  // Asserts on text only Colophon itself renders (the version strings), not
  // a heading the parent page could produce on its own — otherwise a whole
  // child component can ship unwired while its tests only check a line the
  // parent already renders.
  it("renders the colophon's version rows, not just its heading", () => {
    renderAbout();
    expect(screen.getByText(zh["about.colophonFrontend"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonBackend"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonComputation"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonModel"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonDatabases"])).toBeInTheDocument();
  });

  // The colophon's row labels (Frontend/Backend/...)
  // are ordinary translatable nouns, not database/format jargon, so they
  // must actually switch with locale rather than sitting on screen as a
  // fixed English literal regardless of language.
  it("translates the colophon's row labels, not just its values", () => {
    renderAbout();
    expect(screen.getByText(zh["about.colophonFrontendLabel"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonBackendLabel"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonComputationLabel"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonModelLabel"])).toBeInTheDocument();
    expect(screen.getByText(zh["about.colophonDatabasesLabel"])).toBeInTheDocument();
  });

  it("uses the English colophon row labels at locale=en", async () => {
    localStorage.setItem(LOCALE_KEY, "en");
    try {
      renderAbout();
      await waitFor(() => expect(screen.getByText(en["about.title"]!)).toBeInTheDocument());
      expect(screen.getByText(en["about.colophonFrontendLabel"]!)).toBeInTheDocument();
      expect(screen.getByText(en["about.colophonBackendLabel"]!)).toBeInTheDocument();
      expect(screen.getByText(en["about.colophonComputationLabel"]!)).toBeInTheDocument();
      expect(screen.getByText(en["about.colophonModelLabel"]!)).toBeInTheDocument();
      expect(screen.getByText(en["about.colophonDatabasesLabel"]!)).toBeInTheDocument();
    } finally {
      localStorage.removeItem(LOCALE_KEY);
    }
  });
});
