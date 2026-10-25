import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider, LOCALE_KEY } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import Content from "../Content";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/src/services/post", () => ({ addChat: vi.fn() }));

function renderContent() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <LocaleProvider><Content /></LocaleProvider>
    </QueryClientProvider>,
  );
}

describe("Content (/chat welcome screen)", () => {
  // The user named this explicitly on 2026-08-04: the Chinese phrase for
  // "or just chat with you" had to go. The market already has enough
  // chatbots, and a page that invites chit-chat gets chit-chat -- after
  // which the backend's scope guardrail can only keep declining it, which
  // is a worse experience than never inviting it in the first place. This
  // welcome copy is the physician's first sentence in the whole
  // interaction, and it sets the expectation for everything that follows.
  it("does not invite chit-chat", () => {
    renderContent();
    expect(screen.queryByText(/陪你聊天/)).toBeNull();
    expect(screen.queryByText(/想聊些什麼/)).toBeNull();
  });

  it("states the four in-scope topics", () => {
    renderContent();
    // Assert on the scope paragraph itself, not the whole page via a single
    // getByText -- the title also contains the Chinese word for
    // "metabolomics", so a page-wide getByText throws "Found multiple
    // elements" (how the first version of this test failed).
    const scope = screen.getByText(/範圍之外/);
    for (const topic of ["代謝體學", "代謝途徑", "統計", "圖表"]) {
      expect(scope.textContent).toContain(topic);
    }
  });

  it("suggestions map to real supported capabilities", () => {
    renderContent();
    // The three suggestions correspond to analysis / id_mapping /
    // plot_review. They are the only clickable demonstration of "what this
    // tool can do" and must not be arbitrary sentences. The suggestions are
    // now a left-aligned list of <a> rows (roman numerals) rather than pill
    // <button>s, so this queries links, filtered down to the suggestion
    // rows via their accessible name.
    const links = screen.getAllByRole("link", { name: /顯著差異|PubChem|投稿規範/ });
    expect(links.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/顯著差異/)).toBeInTheDocument();
    expect(screen.getByText(/投稿規範|期刊/)).toBeInTheDocument();
  });

  it("clicking a suggestion fills the composer without submitting", async () => {
    const { addChat } = await import("@/src/services/post");
    renderContent();

    await userEvent.click(screen.getByText(/顯著差異/));

    expect(screen.getByPlaceholderText(zh["chat.inputPlaceholder"])).toHaveValue(
      zh["chat.suggest1"],
    );
    // Filling the composer is not the same as sending a message -- a
    // suggestion is a demonstration to fill in and let the physician edit
    // or confirm, not an auto-submit.
    expect(addChat).not.toHaveBeenCalled();
  });

  // A reviewer tests with the English UI, and this welcome screen is the
  // first page they see. The original copy was hardcoded Chinese, invisible
  // to that reviewer.
  it("shows English copy when locale=en", async () => {
    window.localStorage.setItem(LOCALE_KEY, "en");
    try {
      renderContent();
      // LocaleProvider reads localStorage only inside a useEffect (to avoid
      // an SSR/CSR hydration mismatch), so the first render is still zh --
      // wait for the switch before asserting.
      await waitFor(() =>
        expect(screen.getByText(/Metabolomics Research Assistant/i)).toBeInTheDocument());
      expect(screen.queryByText(/陪你聊天/)).toBeNull();
      expect(screen.getByText(/I do not answer questions outside that scope/i))
        .toBeInTheDocument();
    } finally {
      window.localStorage.removeItem(LOCALE_KEY);
    }
  });

  // A child component can ship as dead code if its tests assert only on a
  // line the *parent* renders, since they stay green with the child
  // unwired. Assert on something only Composer renders -- its input
  // placeholder -- not on text Content.tsx could produce on its own.
  it("renders the shared Composer, not a second hand-rolled input", () => {
    renderContent();
    expect(screen.getByPlaceholderText(zh["chat.inputPlaceholder"])).toBeInTheDocument();
  });
});
