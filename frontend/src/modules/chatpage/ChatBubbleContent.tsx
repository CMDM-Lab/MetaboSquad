"use client";

import { API_BASE } from "@/src/config/constants";
import { useT } from "@/src/i18n/LocaleContext";
import type { ResultBlockData, TraceStep } from "@/src/types/results";
import ResultCard from "@/src/modules/results/ResultCard";
import AgentTrace from "./AgentTrace";

type Block = Record<string, unknown> & { type?: string };

/**
 * Message content block dispatcher. Supports the text / image / result /
 * trace block types; unknown types are ignored.
 *
 * Important: when an `analysis` run finishes, the backend's last message is
 * an intermediate node's text (`save_significant_node` does not return
 * `messages`), so whenever a result block is also present, the text is
 * downgraded to a footnote rather than let a physician misread a mid-run
 * message as the conclusion.
 */
export default function ChatBubbleContent({
  content,
  messageId,
  role,
  panelResultMessageId,
}: {
  content: unknown;
  messageId?: number;
  /** Whether this message is "user" or "assistant". The backend persists
   * user messages in the exact same shape as an assistant text block
   * (`chat.py`'s `content_list = [{"type": "text", "text": req.message}]`),
   * and `/history` returns user messages alongside assistant ones, so this
   * prop is what tells the two apart for styling. */
  role?: string;
  /** The id of the message whose `analysis`-intent result ChatWindow is
   * currently showing in the thread's side panel (its
   * `findLatestAnalysisResult()` always picks the *latest* one). Only that
   * one message's analysis card is suppressed here — an earlier analysis
   * run in the same thread still renders inline, so a physician who reruns
   * an analysis does not lose the first result they were comparing
   * against. Undefined (no analysis result exists yet) suppresses nothing. */
  panelResultMessageId?: number;
}) {
  const { t } = useT();

  if (content == null) return null;
  if (typeof content === "string") return <>{content}</>;
  if (!Array.isArray(content)) return null;

  const blocks = content.filter(
    (b): b is Block => !!b && typeof b === "object",
  );
  const hasResult = blocks.some((b) => b.type === "result");
  const isUser = role === "user";

  return (
    // Deliberately not a flex container: the per-message turn wrapper in
    // ChatWindow.tsx is what right-aligns the user turn (`items-end` there),
    // by shrinking *this* div to fit its content via that outer flex
    // context. A nested `display:flex` here would fight that shrink-to-fit
    // sizing against each block's own `max-width`. Plain block flow with
    // `space-y` keeps the two concerns (outer alignment, inner stacking)
    // independent.
    <div className="space-y-[var(--space-3)]">
      {blocks.map((b, idx) => {
        if (b.type === "text" && typeof b.text === "string") {
          if (hasResult) {
            return (
              <p
                key={idx}
                data-testid="text-fallback"
                className="whitespace-pre-wrap border-l-2 border-neutral-300 pl-[var(--space-2)] text-[12px] text-neutral-500"
              >
                {b.text}
                <span className="mt-1 block opacity-70">
                  {t("result.textFallbackNote")}
                </span>
              </p>
            );
          }
          // The user turn is right-aligned with a
          // 60ch measure and a neutral-400 rule; the assistant turn is full
          // width, 15px/1.65 and start-aligned — never justified, since
          // justified CJK at a narrow measure breaks tokens like
          // `|log₂FC| > 1` across lines. `textAlign` is set inline (rather
          // than relying on the browser default) so it is both explicit and
          // visible to jsdom's `toHaveStyle` in tests.
          return (
            <span
              key={idx}
              className={
                isUser
                  ? "block max-w-[60ch] whitespace-pre-wrap border-l-2 border-neutral-400 pl-[var(--space-3)]"
                  : "block w-full whitespace-pre-wrap text-[15px] leading-[1.65]"
              }
              style={isUser ? undefined : { textAlign: "start" }}
            >
              {b.text}
            </span>
          );
        }

        if (b.type === "image" && typeof b.url === "string") {
          const src = `${API_BASE}${b.url}`;
          return (
            <div key={idx} className="flex flex-col gap-[var(--space-2)]">
              <img
                src={src}
                alt={t("chat.imageAlt")}
                className="max-h-80 max-w-full border border-divider object-contain"
              />
              <a
                href={src}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex text-[12px]"
              >
                {t("result.tabFiles")}
              </a>
            </div>
          );
        }

        if (b.type === "result") {
          const intent = (b.intent as string) ?? null;
          // Layout B: only the `analysis` intent's *newest* result mounts in the thread's
          // side panel — ChatWindow.tsx renders it there from the history
          // payload. Suppressing every analysis block unconditionally (an
          // earlier bug) makes a second analysis in the same thread delete
          // the first one's significant metabolites, figures and folder
          // artifacts from the page entirely — a physician comparing two
          // runs would silently lose the one they ran first. So this only
          // suppresses the one message the panel is actually showing
          // (matched by messageId); every other analysis-intent message,
          // including earlier ones in the same thread, keeps rendering
          // inline exactly like the other three intents.
          const isPanelResult =
            intent === "analysis" &&
            messageId !== undefined &&
            messageId === panelResultMessageId;
          if (isPanelResult) return null;
          return (
            <ResultCard
              key={idx}
              intent={intent}
              data={(b.data as ResultBlockData) ?? {}}
              folder={(b.folder as string) ?? null}
            />
          );
        }

        if (b.type === "trace" && Array.isArray(b.steps)) {
          return (
            <AgentTrace
              key={idx}
              steps={b.steps as TraceStep[]}
              running={false}
            />
          );
        }

        return null;
      })}
    </div>
  );
}
