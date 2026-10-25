import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import Composer from "../Composer";

// Composer embeds the existing FileUpload uploader, which calls useMutation
// internally, so every render needs a QueryClientProvider (mirrors
// UploadFlie.test.tsx / AskConsole.test.tsx).
function renderComposer(overrides: Partial<ComponentProps<typeof Composer>> = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const props: ComponentProps<typeof Composer> = {
    value: "",
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onAbort: vi.fn(),
    pending: false,
    attachedPath: null,
    onAttach: vi.fn(),
    onAttachError: vi.fn(),
    maxWidth: 1240,
    ...overrides,
  };
  const utils = render(
    <QueryClientProvider client={qc}>
      <LocaleProvider><Composer {...props} /></LocaleProvider>
    </QueryClientProvider>,
  );
  return { ...utils, props };
}

describe("Composer", () => {
  it("renders the attach control, the input and the send button", () => {
    renderComposer();
    expect(screen.getByRole("button", { name: zh["chat.attach"] })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(zh["chat.inputPlaceholder"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zh["chat.send"] })).toBeInTheDocument();
  });

  it("applies the maxWidth prop to the inner row", () => {
    renderComposer({ maxWidth: 900 });
    const input = screen.getByPlaceholderText(zh["chat.inputPlaceholder"]);
    // The row wrapping attach/input/send is the input's own parent.
    expect(input.parentElement).toHaveStyle({ maxWidth: "900px" });
  });

  it("typing calls onChange with the new value", async () => {
    const onChange = vi.fn();
    renderComposer({ onChange });

    await userEvent.type(screen.getByPlaceholderText(zh["chat.inputPlaceholder"]), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("pressing Enter (not composing) calls onSubmit", () => {
    const onSubmit = vi.fn();
    renderComposer({ onSubmit });

    fireEvent.keyDown(screen.getByPlaceholderText(zh["chat.inputPlaceholder"]), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  // Guards against submitting mid-IME-composition — without this, every
  // Chinese sentence would send on the first character selected in the
  // candidate window.
  it("Enter during IME composition does not call onSubmit", () => {
    const onSubmit = vi.fn();
    renderComposer({ onSubmit });

    fireEvent.keyDown(
      screen.getByPlaceholderText(zh["chat.inputPlaceholder"]),
      { key: "Enter", isComposing: true },
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("clicking send calls onSubmit", async () => {
    const onSubmit = vi.fn();
    renderComposer({ onSubmit });

    await userEvent.click(screen.getByRole("button", { name: zh["chat.send"] }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  // While streaming, the send button reuses the existing abort wiring
  // exactly — it does not reimplement it — so it must read chat.sending
  // and call onAbort, not onSubmit, when clicked.
  it("while pending, the button reads chat.sending and calls onAbort instead of onSubmit", async () => {
    const onSubmit = vi.fn();
    const onAbort = vi.fn();
    renderComposer({ pending: true, onSubmit, onAbort });

    expect(screen.queryByRole("button", { name: zh["chat.send"] })).not.toBeInTheDocument();
    // The visible label is chat.sending, but the accessible name (aria-label)
    // is chat.stop — a screen-reader user must be told this button aborts,
    // not that it's just a status indicator. getByRole matches by accessible
    // name, so this also proves the aria-label is actually wired.
    const button = screen.getByRole("button", { name: zh["chat.stop"] });
    expect(button).toHaveTextContent(zh["chat.sending"]);
    expect(button).toHaveAttribute("title", zh["chat.stop"]);

    await userEvent.click(button);
    expect(onAbort).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the input while pending", () => {
    renderComposer({ pending: true });
    expect(screen.getByPlaceholderText(zh["chat.inputPlaceholder"])).toBeDisabled();
  });

  // The welcome screen (Content.tsx) has no stream to abort before a thread
  // exists, so it passes no `onAbort` at all. Without this, the component
  // used to force every caller to supply a meaningless no-op; now the
  // pending state must render a disabled status indicator instead of a
  // clickable button that does nothing.
  it("without onAbort, pending renders a disabled button instead of a dead abort affordance", () => {
    renderComposer({ pending: true, onAbort: undefined });

    const button = screen.getByRole("button", { name: zh["chat.sending"] });
    expect(button).toBeDisabled();
    // No stop/abort accessible name should be exposed when there is nothing
    // to abort.
    expect(screen.queryByRole("button", { name: zh["chat.stop"] })).not.toBeInTheDocument();
  });
});
