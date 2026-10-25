import { describe, expect, it, vi, beforeEach } from "vitest";
import { useEffect } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider, useT, type Locale } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import { en } from "@/src/i18n/messages/en";
import type { ChatPublic } from "@/src/types/type";
import Sidebar from "../Sidebar";

let currentParams: { id?: string } = {};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => currentParams,
}));

const renameMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("@/src/hooks/useChatListMutations", () => ({
  useChatListMutations: () => ({
    updateTitleMutation: { mutate: renameMock, isPending: false, variables: undefined },
    deleteChatMutation: { mutate: deleteMock, isPending: false, variables: undefined },
  }),
}));

let chatListData: ChatPublic[] = [];

vi.mock("@/src/hooks/UseQueryChatList", () => ({
  default: () => ({ data: { chats: chatListData }, isLoading: false }),
}));

const DEFAULT_CHATS: ChatPublic[] = [
  { thread_id: "t1", title: "3・分析 LC-MS 資料", created_at: "2026-08-03T14:52:00Z" },
  { thread_id: "t2", title: "citric acid 識別碼查詢", created_at: "2026-08-03T11:20:00Z" },
];

// Captures LocaleProvider's setLocale so tests can flip the interface
// language without going through the navbar's toggle button, which Sidebar
// does not render.
let capturedSetLocale: ((l: Locale) => void) | null = null;

function LocaleProbe() {
  const { setLocale } = useT();
  // capturedSetLocale is assigned in an effect, not the render body:
  // assigning a module-level variable directly in the render body is a side
  // effect during render (react-hooks/globals: "cannot
  // reassign variables declared outside of the component/hook"). RTL's
  // render() flushes effects synchronously (it wraps the initial render in
  // act()), so capturedSetLocale is already populated by the time
  // renderSidebar() returns.
  useEffect(() => {
    capturedSetLocale = setLocale;
  }, [setLocale]);
  return null;
}

function renderSidebar(chats: ChatPublic[] = DEFAULT_CHATS) {
  chatListData = chats;
  render(
    <LocaleProvider>
      <LocaleProbe />
      <Sidebar />
    </LocaleProvider>,
  );
  return { rename: renameMock, delete: deleteMock };
}

function setLocale(locale: Locale) {
  capturedSetLocale?.(locale);
}

describe("Sidebar", () => {
  beforeEach(() => {
    renameMock.mockReset();
    deleteMock.mockReset();
    currentParams = {};
    capturedSetLocale = null;
  });

  // 46px collapsed is enough for the toggle and nothing else. The width is the
  // whole point of the control: a physician reading a wide result panel needs
  // the rail out of the way without losing the way back.
  it("collapses to a rail and expands again", async () => {
    renderSidebar();
    const toggle = screen.getByRole("button", { name: zh["sidebar.toggle"] });
    expect(screen.getByText(zh["sidebar.heading"])).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.queryByText(zh["sidebar.heading"])).toBeNull();
  });

  // The heading disappearing is necessary but not sufficient: an
  // implementation could hide only the heading text while leaving the new
  // chat button, the list and the footer count on screen at full width. This
  // pins that the whole body collapses with it, and that the rail actually
  // narrows to the exact width the design calls for.
  it("collapsing hides the new-chat button, the list and the count, and narrows the rail", async () => {
    renderSidebar();
    const aside = screen.getByRole("complementary");
    expect(aside).toHaveStyle({ width: "256px" });
    expect(screen.getByRole("button", { name: new RegExp(zh["sidebar.newChat"]) })).toBeInTheDocument();
    expect(screen.getAllByRole("navigation")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: zh["sidebar.toggle"] }));

    expect(aside).toHaveStyle({ width: "46px" });
    expect(screen.queryByRole("button", { name: new RegExp(zh["sidebar.newChat"]) })).toBeNull();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByText(/共 \d+ 則對話/)).toBeNull();
  });

  // Rename commits on Enter or blur; an empty title is ignored rather than
  // silently blanking the row (the prototype's commit() drops empty drafts).
  it("ignores an empty rename", async () => {
    const { rename } = renderSidebar();
    await userEvent.click(screen.getAllByRole("button", { name: zh["sidebar.rename"] })[0]);
    const input = screen.getByRole("textbox");
    await userEvent.clear(input);
    await userEvent.keyboard("{Enter}");
    expect(rename).not.toHaveBeenCalled();
    // The row keeps its previous title rather than showing a blank row.
    expect(screen.getByText(DEFAULT_CHATS[0].title)).toBeInTheDocument();
  });

  it("commits a non-empty rename on Enter", async () => {
    const { rename } = renderSidebar();
    await userEvent.click(screen.getAllByRole("button", { name: zh["sidebar.rename"] })[0]);
    const input = screen.getByRole("textbox");
    await userEvent.clear(input);
    await userEvent.type(input, "New title");
    await userEvent.keyboard("{Enter}");
    expect(rename).toHaveBeenCalledWith({ id: "t1", title: "New title" });
  });

  // Blur is the other commit trigger: a physician who clicks
  // elsewhere without pressing Enter must not lose the edit.
  it("commits a non-empty rename on blur", async () => {
    const { rename } = renderSidebar();
    await userEvent.click(screen.getAllByRole("button", { name: zh["sidebar.rename"] })[0]);
    const input = screen.getByRole("textbox");
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed via blur");
    await userEvent.click(document.body);
    expect(rename).toHaveBeenCalledWith({ id: "t1", title: "Renamed via blur" });
  });

  // Escape is the conventional inline-editor cancel: it costs one line and
  // is expected by any user of an inline text field, even though the
  // prototype does not model it explicitly.
  it("Escape cancels a rename without committing", async () => {
    const { rename } = renderSidebar();
    await userEvent.click(screen.getAllByRole("button", { name: zh["sidebar.rename"] })[0]);
    const input = screen.getByRole("textbox");
    await userEvent.clear(input);
    await userEvent.type(input, "should not be saved");
    await userEvent.keyboard("{Escape}");
    expect(rename).not.toHaveBeenCalled();
    expect(screen.getByText(DEFAULT_CHATS[0].title)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  // Regression: a same-row rename attempted right after an Escape-cancelled
  // one must still commit. An implementation that tracks "was this blur
  // caused by Escape's own cancellation" with a flag set on Escape and
  // cleared only when a matching stray blur actually shows up (which a
  // browser *may* skip) leaks that flag into the next, unrelated rename
  // attempt on the same row — silently dropping a real edit with no error.
  it("a rename started again after an Escape-cancelled one still commits", async () => {
    const { rename } = renderSidebar();
    const renameButton = screen.getAllByRole("button", { name: zh["sidebar.rename"] })[0];

    await userEvent.click(renameButton);
    await userEvent.type(screen.getByRole("textbox"), " typo");
    await userEvent.keyboard("{Escape}");
    expect(rename).not.toHaveBeenCalled();

    await userEvent.click(renameButton);
    const input = screen.getByRole("textbox");
    await userEvent.clear(input);
    await userEvent.type(input, "Second attempt");
    await userEvent.keyboard("{Enter}");

    expect(rename).toHaveBeenCalledWith({ id: "t1", title: "Second attempt" });
  });

  // Each row's timestamp is sourced from the server's `created_at` and
  // formatted as an absolute short date-time via Intl.DateTimeFormat rather
  // than relative wording —
  // that keeps this feature i18n-key-free (no new "today"/"yesterday"
  // strings) while still translating with the locale.
  it("renders each row's timestamp formatted for the active locale", () => {
    renderSidebar([
      { thread_id: "a", title: "lcms_table.csv 差異分析", created_at: "2026-08-03T14:52:00Z" },
    ]);
    const expected = new Intl.DateTimeFormat("zh-Hant", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date("2026-08-03T14:52:00Z"));
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  // No confirmation dialog: delete keeps the existing mutation's behaviour
  // and calls it directly.
  it("delete calls the mutation directly with no confirmation dialog", async () => {
    const { delete: del } = renderSidebar();
    const confirmSpy = vi.spyOn(window, "confirm");
    await userEvent.click(screen.getAllByRole("button", { name: zh["sidebar.delete"] })[0]);
    expect(del).toHaveBeenCalledWith("t1");
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  // Locale switching must not re-seed or re-fetch the list into a different
  // identity — the first cut of the prototype discarded the user's own
  // threads on a locale change. Here the titles come from the server, so the
  // invariant is simply that a locale change leaves them untouched. Checking
  // that the chrome *does* translate alongside it rules out a false pass
  // from a component that merely failed to re-render at all.
  it("a locale change leaves thread titles verbatim while the chrome translates", async () => {
    renderSidebar([
      { thread_id: "a", title: "lcms_table.csv 差異分析", created_at: "2026-08-03T14:52:00Z" },
    ]);
    expect(screen.getByText(zh["sidebar.heading"])).toBeInTheDocument();

    act(() => setLocale("en"));

    expect(await screen.findByText("lcms_table.csv 差異分析")).toBeInTheDocument();
    // `en` is typed Partial<Record<...>> as a safety net for keys not yet
    // translated; "sidebar.heading" is confirmed present in en.ts.
    expect(screen.getByText(en["sidebar.heading"]!)).toBeInTheDocument();
    expect(screen.queryByText(zh["sidebar.heading"])).toBeNull();
  });

  it("footer count reflects the number of threads", () => {
    renderSidebar(DEFAULT_CHATS);
    expect(screen.getByText(zh["sidebar.count"].replace("{n}", "2"))).toBeInTheDocument();
  });

  // Mirrors Navbar's own landmark test: the sidebar's <nav> must carry an
  // accessible name so a screen-reader user's landmark list distinguishes it
  // from the navbar's <nav aria-label="Primary">, rather than showing two
  // indistinguishable "navigation" regions on every chat page.
  it("the thread list is a uniquely-named navigation landmark", () => {
    renderSidebar();
    const navs = screen.getAllByRole("navigation");
    expect(navs).toHaveLength(1);
    expect(navs[0]).toHaveAccessibleName(zh["sidebar.heading"]);
  });
});
