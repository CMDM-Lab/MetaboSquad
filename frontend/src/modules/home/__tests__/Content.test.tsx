import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider, LOCALE_KEY } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import { en } from "@/src/i18n/messages/en";
import { ApiError } from "@/src/lib/apiClient";
import { addChat } from "@/src/services/post";
import Content from "../Content";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));
// Content only calls addChat(); FileUpload (embedded via AskConsole) imports
// uploadFile from the same module but never calls it unless a test actually
// uploads a file, so leaving it out of this mock is safe — mirrors
// modules/chatpage/__tests__/Content.test.tsx.
vi.mock("@/src/services/post", () => ({ addChat: vi.fn() }));

const mockedAddChat = vi.mocked(addChat);

function renderHome() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <LocaleProvider>
        <Content />
      </LocaleProvider>
    </QueryClientProvider>,
  );
}

describe("Content (home /)", () => {
  beforeEach(() => {
    push.mockReset();
    mockedAddChat.mockReset();
  });

  // The console is deliberately the loudest element on the page: it is the
  // whole interaction model. A physician who cannot find where to type has
  // no path in.
  it("renders the plain-language console with attach, input and send", () => {
    renderHome();
    expect(screen.getByText(zh["home.askKicker"])).toBeInTheDocument();
    expect(screen.getByPlaceholderText(zh["home.askPlaceholder"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zh["chat.send"] })).toBeInTheDocument();
  });

  // The three ledger entries are the only statement of scope on the landing
  // page, and one of them must send the reader to /tools rather than into a
  // chat.
  it("the capability ledger links to chat and to tools", () => {
    renderHome();
    const links = screen.getAllByRole("link");
    expect(links.some((a) => a.getAttribute("href") === "/tools")).toBe(true);
    expect(links.filter((a) => a.getAttribute("href") === "/chat").length).toBe(2);
  });

  it("renders English copy at locale=en", async () => {
    localStorage.setItem(LOCALE_KEY, "en");
    try {
      renderHome();
      await waitFor(() =>
        expect(screen.getByText(en["home.capTitle"]!)).toBeInTheDocument());
    } finally {
      localStorage.removeItem(LOCALE_KEY);
    }
  });

  // Preserves the pre-redesign addChat -> router.push flow byte-for-byte:
  // only the markup around it changed.
  it("submitting a question creates a chat and navigates with the message encoded", async () => {
    mockedAddChat.mockResolvedValue({
      thread_id: "abc123",
      title: "",
      created_at: "2026-01-01T00:00:00Z",
    });
    renderHome();

    await userEvent.type(
      screen.getByPlaceholderText(zh["home.askPlaceholder"]),
      "citric acid",
    );
    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/chat/abc123?firstMsg=citric%20acid"));
  });

  it("shows the backend's ApiError detail verbatim on failure", async () => {
    mockedAddChat.mockRejectedValue(new ApiError(500, "伺服器忙碌中"));
    renderHome();

    await userEvent.type(screen.getByPlaceholderText(zh["home.askPlaceholder"]), "test");
    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));

    expect(await screen.findByText("伺服器忙碌中")).toBeInTheDocument();
  });

  // The dropped-connection TypeError is also an instance of Error; showing
  // its .message would print untranslated English at a physician.
  it("falls back to the translated network message for a plain Error, not error.message", async () => {
    mockedAddChat.mockRejectedValue(new TypeError("Failed to fetch"));
    renderHome();

    await userEvent.type(screen.getByPlaceholderText(zh["home.askPlaceholder"]), "test");
    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));

    expect(await screen.findByText(zh["error.network"])).toBeInTheDocument();
    expect(screen.queryByText("Failed to fetch")).toBeNull();
  });
});
