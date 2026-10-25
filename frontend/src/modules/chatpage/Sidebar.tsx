"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChevronsLeft, ChevronsRight, Pencil, X } from "lucide-react";
import useQueryChatList from "@/src/hooks/UseQueryChatList";
import { useChatListMutations } from "@/src/hooks/useChatListMutations";
import { useT } from "@/src/i18n/LocaleContext";
import type { Locale } from "@/src/i18n/LocaleContext";
import type { ChatPublic } from "@/src/types/type";

const EXPANDED_WIDTH = "256px";
const COLLAPSED_WIDTH = "46px";

// The design mock shows relative wording (a Chinese "today HH:MM" form, or
// "Aug 3" in English), which would need new "today"/"yesterday" i18n
// strings. An absolute short date-time in mono tabular figures needs no new
// copy and reads closer to the instrument idiom the rest of the UI uses for
// numerals, so this deviates from the mock on purpose.
const INTL_LOCALE: Record<Locale, string> = { zh: "zh-Hant", en: "en" };

function formatTimestamp(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export default function Sidebar() {
  const { t, locale } = useT();
  const router = useRouter();
  const params = useParams();
  const activeId = params?.id as string | undefined;

  const [open, setOpen] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const { data } = useQueryChatList();
  const chats = data?.chats ?? [];

  const { deleteChatMutation, updateTitleMutation } = useChatListMutations({
    activeThreadId: activeId,
  });

  const onAddNewChat = () => router.push("/chat");
  const onSelectConversation = (id: string) => router.push(`/chat/${id}`);

  const startRename = (chat: ChatPublic) => {
    setEditingId(chat.thread_id);
    setDraft(chat.title);
  };

  const cancelRename = (chat: ChatPublic) => {
    // Resetting the draft back to the row's current title (rather than just
    // clearing editingId) is what makes commitRename's own
    // "next === chat.title" check absorb a stray blur that a real browser
    // can dispatch when a focused input is removed from the DOM — no
    // separate ref/flag needed, and no risk of that flag leaking into and
    // silently swallowing the *next* rename attempt on this row.
    setEditingId(null);
    setDraft(chat.title);
  };

  const commitRename = (chat: ChatPublic) => {
    const next = draft.trim();
    setEditingId(null);
    // An empty or whitespace-only draft is ignored: the row keeps its
    // previous title and no mutation fires. This is what stops a physician
    // blanking a thread title by tabbing away mid-edit. It also absorbs any
    // stray post-Escape blur, since cancelRename leaves draft === chat.title.
    if (!next || next === chat.title) return;
    updateTitleMutation.mutate({ id: chat.thread_id, title: next });
  };

  return (
    <aside
      // The collapse rail's exact widths are a layout-critical value the
      // sidebar test observes directly (jsdom's toHaveStyle only sees inline
      // styles, not compiled Tailwind), so they are set inline.
      style={{ width: open ? EXPANDED_WIDTH : COLLAPSED_WIDTH }}
      className="flex h-full flex-none flex-col overflow-hidden border-r border-neutral-900 bg-neutral-100"
    >
      <div className="flex min-h-[44px] items-center gap-[var(--space-2)] border-b border-divider px-[var(--space-2)]">
        <button
          type="button"
          aria-label={t("sidebar.toggle")}
          onClick={() => setOpen((o) => !o)}
          className="btn btn-secondary h-[30px] w-[30px] flex-none p-0"
        >
          {open ? <ChevronsLeft size={16} /> : <ChevronsRight size={16} />}
        </button>
        {open && (
          // 9.5px, not the design mock's literal 9px: the typography floor
          // for uppercase mono labels is 9.5px, and a legibility floor
          // protects the reader, so the stricter value wins here (unlike a
          // visual-identity choice, where the mock governs — see the
          // accent-600/700 kicker decision in AskConsole.tsx).
          <span className="whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.16em] text-neutral-600">
            {t("sidebar.heading")}
          </span>
        )}
      </div>

      {open && (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="p-[var(--space-2)]">
            <button
              type="button"
              className="btn btn-primary btn-block mt-0"
              onClick={onAddNewChat}
            >
              {"＋ "}
              {t("sidebar.newChat")}
            </button>
          </div>

          {/* Named so this isn't a second unnamed navigation landmark
              alongside the navbar's <nav aria-label="Primary">. */}
          <nav
            aria-label={t("sidebar.heading")}
            className="min-h-0 flex-1 overflow-y-auto border-t border-divider"
          >
            {chats.map((chat) => {
              const isActive = activeId === chat.thread_id;
              const isEditing = editingId === chat.thread_id;
              const renamePending =
                updateTitleMutation.isPending &&
                updateTitleMutation.variables?.id === chat.thread_id;
              const deletePending =
                deleteChatMutation.isPending &&
                deleteChatMutation.variables === chat.thread_id;

              return (
                <div
                  key={chat.thread_id}
                  className={`group grid grid-cols-[1fr_auto] items-center gap-[var(--space-2)] border-b border-neutral-200 py-[var(--space-2)] pr-[var(--space-2)] pl-0 ${
                    isActive ? "border-l-2 border-accent-600 bg-surface" : "border-l-2 border-transparent"
                  }`}
                >
                  {isEditing ? (
                    <input
                      autoFocus
                      className="input ml-[var(--space-2)] min-h-[28px] bg-white text-[12.5px]"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={() => commitRename(chat)}
                      onKeyDown={(e) => {
                        // The Enter guard mirrors the composer's IME check
                        // elsewhere in this app: a physician confirming a
                        // Chinese IME composition with Enter must not commit
                        // a half-typed title.
                        if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                          commitRename(chat);
                        } else if (e.key === "Escape") {
                          cancelRename(chat);
                        }
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => onSelectConversation(chat.thread_id)}
                      className={`min-w-0 border-0 bg-transparent p-0 pl-[var(--space-3)] text-left ${
                        isActive ? "text-text" : "text-neutral-700"
                      }`}
                    >
                      <span
                        className={`block overflow-hidden text-ellipsis whitespace-nowrap text-[12.5px] ${
                          isActive ? "font-semibold" : "font-normal"
                        }`}
                      >
                        {chat.title}
                      </span>
                      <span className="mt-[2px] block font-mono text-[9.5px] tabular-nums text-neutral-500">
                        {formatTimestamp(chat.created_at, locale)}
                      </span>
                    </button>
                  )}

                  <div className="mm-acts flex gap-[2px] opacity-0 group-hover:opacity-100 group-focus-within:opacity-100">
                    <button
                      type="button"
                      aria-label={t("sidebar.rename")}
                      disabled={renamePending || deletePending}
                      onClick={() => startRename(chat)}
                      className="btn btn-secondary h-[24px] w-[24px] border-transparent bg-transparent p-0 text-neutral-600"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      aria-label={t("sidebar.delete")}
                      disabled={renamePending || deletePending}
                      onClick={() => deleteChatMutation.mutate(chat.thread_id)}
                      className="btn btn-secondary h-[24px] w-[24px] border-transparent bg-transparent p-0 text-neutral-600"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </nav>

          <div className="border-t border-divider p-[var(--space-2)] font-mono text-[9.5px] uppercase tracking-[0.12em] text-neutral-500">
            {t("sidebar.count", { n: chats.length })}
          </div>
        </div>
      )}
    </aside>
  );
}
