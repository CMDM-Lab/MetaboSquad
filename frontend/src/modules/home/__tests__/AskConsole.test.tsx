import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import AskConsole from "../AskConsole";

// AskConsole embeds the existing FileUpload uploader, which calls
// useMutation internally, so every render needs a QueryClientProvider —
// mirrors modules/chatpage/__tests__/UploadFlie.test.tsx.
function renderConsole(overrides: Partial<ComponentProps<typeof AskConsole>> = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const props: ComponentProps<typeof AskConsole> = {
    onSubmit: vi.fn(),
    pending: false,
    attachedFilePath: null,
    onAttachSuccess: vi.fn(),
    onAttachError: vi.fn(),
    ...overrides,
  };
  const utils = render(
    <QueryClientProvider client={qc}>
      <LocaleProvider>
        <AskConsole {...props} />
      </LocaleProvider>
    </QueryClientProvider>,
  );
  return { ...utils, props };
}

describe("AskConsole", () => {
  // The console is the whole interaction model: a visitor who cannot find
  // where to type has no path in.
  it("renders the plain-language console with attach, input and send", () => {
    renderConsole();
    expect(screen.getByText(zh["home.askKicker"])).toBeInTheDocument();
    expect(screen.getByPlaceholderText(zh["home.askPlaceholder"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zh["chat.send"] })).toBeInTheDocument();
  });

  // A suggestion click fills the composer AND
  // records the intent. Filling only the text loses the intent the
  // suggestion encoded.
  it("a suggestion click fills the input and records its intent", async () => {
    const onSubmit = vi.fn();
    renderConsole({ onSubmit });

    await userEvent.click(screen.getByText(zh["chat.suggest2"]));
    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));

    expect(onSubmit).toHaveBeenCalledWith(zh["chat.suggest2"], "id_mapping");
  });

  // Editing the text after a suggestion filled it means the words are no
  // longer the suggestion verbatim, so the recorded intent must not survive.
  it("typing over a filled suggestion drops the recorded intent", async () => {
    const onSubmit = vi.fn();
    renderConsole({ onSubmit });

    await userEvent.click(screen.getByText(zh["chat.suggest1"]));
    const input = screen.getByPlaceholderText(zh["home.askPlaceholder"]);
    await userEvent.type(input, "!");
    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));

    expect(onSubmit).toHaveBeenCalledWith(`${zh["chat.suggest1"]}!`, null);
  });

  // Enter must not submit mid-IME-composition, or every Chinese sentence
  // sends on the first character selected.
  it("Enter during IME composition does not submit", async () => {
    const onSubmit = vi.fn();
    renderConsole({ onSubmit });

    const input = screen.getByPlaceholderText(zh["home.askPlaceholder"]);
    await userEvent.type(input, "代謝");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("does not submit blank input", async () => {
    const onSubmit = vi.fn();
    renderConsole({ onSubmit });

    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the input and send button while a request is pending", () => {
    renderConsole({ pending: true });
    expect(screen.getByPlaceholderText(zh["home.askPlaceholder"])).toBeDisabled();
    expect(screen.getByRole("button", { name: zh["chat.send"] })).toBeDisabled();
  });

  // The console is deliberately the loudest element on the page: a 2px ink
  // border on white, not a softened hairline.
  it("keeps the 2px ink border rather than a softened hairline", () => {
    renderConsole();
    expect(screen.getByTestId("ask-console").style.border).toBe("2px solid var(--color-text)");
  });
});
