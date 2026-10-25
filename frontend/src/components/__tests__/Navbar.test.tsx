import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import Navbar from "../Navbar";

let currentPathname = "/";

vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
}));

// Sets the pathname the mocked next/navigation usePathname() returns.
function mockPathname(path: string) {
  currentPathname = path;
}

function renderNavbar() {
  return render(
    <LocaleProvider>
      <Navbar />
    </LocaleProvider>,
  );
}

describe("Navbar", () => {
  beforeEach(() => {
    currentPathname = "/";
  });

  it("shows the four items (home/chat/tools/about), never tasks", () => {
    renderNavbar();

    expect(screen.getByRole("link", { name: "首頁" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "對話" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "工具集" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "關於" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "任務清單" })).not.toBeInTheDocument();
  });

  it("title is MetaboSquad, not the old long English name", () => {
    renderNavbar();

    expect(screen.getByText("MetaboSquad")).toBeInTheDocument();
    expect(screen.queryByText(/Metabolomics Analysis Assistant/)).not.toBeInTheDocument();
  });

  // The gradient-clipped wordmark was the single loudest "side project"
  // signal. The brand is now a two-line block: name plus a mono uppercase
  // tagline.
  it("brand is a two-line block with the mono tagline", () => {
    renderNavbar();

    expect(screen.getByText("MetaboSquad")).toBeInTheDocument();
    expect(screen.getByText("代謝體分析 AI 助理")).toBeInTheDocument();
  });

  it("clicking the locale toggle switches the interface language", async () => {
    renderNavbar();

    expect(screen.getByRole("link", { name: "首頁" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /switch language/i }));

    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
  });

  // aria-current is what the accent colour is keyed to in CSS; if the
  // attribute is missing the active item is styled but not announced.
  it("marks the active route with aria-current", () => {
    mockPathname("/chat");
    renderNavbar();

    expect(screen.getByRole("link", { name: "對話" })).toHaveAttribute("aria-current", "page");
  });

  // Guards against an implementation that sets aria-current="page" on every
  // link regardless of route, which would make the test above pass for the
  // wrong reason.
  it("does not mark an inactive route with aria-current", () => {
    mockPathname("/chat");
    renderNavbar();

    expect(screen.getByRole("link", { name: "首頁" })).not.toHaveAttribute("aria-current");
  });

  // Navbar's root is a <header>, which only maps to the implicit `banner`
  // landmark role when it is not nested inside another sectioning element
  // (HTML-AAM). This pins that Navbar itself renders one banner and one
  // *named* navigation landmark — a nav without an accessible name is
  // indistinguishable from any other unnamed <nav> on the page to a screen
  // reader's landmark list.
  //
  // This only proves Navbar's own subtree, not the full composed document:
  // layout.tsx (which used to wrap <Navbar/> in an extra <nav>, suppressing
  // the banner role) is a Server Component that render-time next/font calls
  // keep RTL from rendering directly, so the wrapper's removal is not
  // covered here.
  it("is the page banner with exactly one named navigation landmark inside", () => {
    renderNavbar();

    expect(screen.getByRole("banner")).toBeInTheDocument();

    const navs = screen.getAllByRole("navigation");
    expect(navs).toHaveLength(1);
    expect(navs[0]).toHaveAccessibleName();
  });
});
