// The clinical thread shell (layout B).
// Structure top to bottom: thread title → wrapping body row
// (conversation column + result panel) → docked composer.

"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useT } from "@/src/i18n/LocaleContext";
import useQueryHistory from "@/src/hooks/UseQueryHistory";
import useQueryChatList from "@/src/hooks/UseQueryChatList";
import useChatStream from "@/src/hooks/useChatStream";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import ResultPanelShell from "@/src/modules/results/ResultPanelShell";
import ResultCard from "@/src/modules/results/ResultCard";
import type { ChatMessageHistory } from "@/src/types/type";
import type { ResultBlockData } from "@/src/types/results";
import ChatBubbleContent from "./ChatBubbleContent";
import ZipDownloadBox from "./ZipDownloadBox";
import AgentTrace from "./AgentTrace";
import Composer from "./Composer";

/**
 * `streamError` (see useChatStream.ts) carries two different kinds of
 * string:
 * - An i18n key ("error.streamAborted" / "error.emptyResponse" /
 *   "error.network") that we set ourselves and must run through `t()`.
 * - The backend's `ApiError.detail`, which is already display-ready Chinese
 *   (e.g. a "conversation not found" message) and is not an i18n key at
 *   all. Running it through `t()` too would make `LocaleContext`
 *   `console.warn` on the missing key and fall back to echoing the string
 *   unchanged — the screen would look right by accident while the console
 *   fills with noise that misleads the next person debugging it.
 * The "error." prefix distinguishes the two: every i18n key in this project
 * follows the "<namespace>.<name>" convention, and a backend detail is a
 * natural-language sentence that will not happen to match that shape.
 */
function resolveStreamErrorText(raw: string, t: (key: string) => string): string {
  return raw.startsWith("error.") ? t(raw) : raw;
}

type HistoryBlock = Record<string, unknown> & { type?: string };

// error.streamAborted and error.duplicateRequest are neutral notices, not
// failures: the physician either stopped the stream
// themselves, or the backend's duplicate-request short-circuit
// (`chat.py`) already answered from history without rerunning the agent.
// Both render through `ErrorCard tone="notice"` — no retry button — using
// the exact display string named here.
const NEUTRAL_NOTICE_KEYS: Record<string, string> = {
  "error.streamAborted": "chat.stopped",
  "error.duplicateRequest": "error.duplicateRequest",
};

/**
 * Finds the most recent `analysis`-intent result block across the thread's
 * persisted history. Layout B only ever shows one result at a time in the
 * side panel, so the latest one wins — matching what ChatBubbleContent
 * would have rendered inline for every other intent.
 */
function findLatestAnalysisResult(messages: ChatMessageHistory[] | undefined) {
  if (!messages) return null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const content = messages[i]?.content;
    if (!Array.isArray(content)) continue;
    const block = (content as HistoryBlock[]).find(
      (b) => b?.type === "result" && b.intent === "analysis",
    );
    if (block) {
      return {
        data: (block.data as ResultBlockData) ?? {},
        folder: (block.folder as string) ?? null,
        messageId: messages[i].id,
      };
    }
  }
  return null;
}

export default function ChatWindow() {
  const { t } = useT();
  const params = useParams(); // The thread id created after sending the first message from the welcome screen.
  const searchParams = useSearchParams(); // Carries the state appended when navigating in (e.g. ?firstMsg=).
  const urlId = params.id as string;
  const firstMsg = searchParams.get("firstMsg");
  const firstImg = searchParams.get("firstImg");

  const [text, setText] = useState(""); // Composer text.
  const [attachedFilePath, setAttachedFilePath] = useState<string | null>(null); // Path of the uploaded attachment.
  const [uploadError, setUploadError] = useState<string | null>(null); // Specific reason an upload failed.
  const autoSendGuardRef = useRef(false); // Prevents the welcome screen's first message from re-sending on every re-render.
  const sendGuardRef = useRef(false); // Prevents a double Enter/click from submitting twice.
  // Remembers the last message actually attempted, so the error card's
  // retry resends that content — not whatever is (usually already cleared)
  // in the input at retry time.
  const lastAttemptRef = useRef<{ message: string; filePath: string | null } | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const { data: historyMessages, isLoading } = useQueryHistory(urlId);
  const { data: chatListData } = useQueryChatList();

  const {
    sendMutation, streamingText, trace, zipFolder, streamError, abort,
  } = useChatStream(urlId);

  const threadTitle =
    chatListData?.chats?.find((c) => c.thread_id === urlId)?.title ?? "";

  const handleSend = (overrideText?: string, overrideFile?: string | null) => {
    const messageContent = overrideText !== undefined ? overrideText : text;
    const filePath = overrideFile !== undefined ? overrideFile : attachedFilePath;

    if (sendMutation.isPending || !messageContent.trim() || sendGuardRef.current) return;

    sendGuardRef.current = true;
    lastAttemptRef.current = { message: messageContent, filePath };
    sendMutation.mutate(
      { message: messageContent, file_path: filePath },
      // The unlock lives in onSettled (not inside mutationFn) so it always
      // fires regardless of success, failure or abort — it used to hang off
      // an unused ref inside useChatStream and never actually unlocked.
      { onSettled: () => { sendGuardRef.current = false; } },
    );
    setText("");
    setAttachedFilePath(null);
  };

  const handleRetry = () => {
    const last = lastAttemptRef.current;
    if (last) handleSend(last.message, last.filePath);
  };

  useEffect(() => {
    if (!urlId || !firstMsg || autoSendGuardRef.current) return;
    autoSendGuardRef.current = true;

    window.history.replaceState(null, "", window.location.pathname);

    handleSend(firstMsg, firstImg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlId, firstMsg, firstImg]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historyMessages, streamingText, trace.length]);

  const neutralNoticeKey = streamError ? NEUTRAL_NOTICE_KEYS[streamError] : undefined;
  const analysisResult = findLatestAnalysisResult(historyMessages);

  return (
    <div className="flex h-full flex-col bg-bg text-text">
      {threadTitle && (
        <div className="shrink-0 border-b border-divider px-[var(--space-6)] py-[var(--space-4)]">
          <h3 className="text-[19px] font-medium">{threadTitle}</h3>
        </div>
      )}

      {/* The wrap is the responsive rule. No media
          query, no JS width measurement — when the row cannot honour the
          520px conversation floor plus the 380px panel floor, the panel
          drops below the conversation instead of crushing it (the failure
          this rule exists to prevent at iPad width). Written as inline
          styles, like ResultPanelShell's matching declarations, so jsdom's
          `toHaveStyle` can see them. */}
      <div
        data-testid="thread-body"
        className="flex-1"
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignContent: "flex-start",
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        <div
          data-testid="thread-convo"
          style={{ flex: "1 1 520px", minWidth: "min(100%, 520px)", padding: "27.6px" }}
        >
          <div className="mx-auto flex max-w-[760px] flex-col gap-[var(--space-6)]">
            {isLoading ? (
              <p className="text-center text-neutral-500">{t("chat.historyLoading")}</p>
            ) : (
              <>
                {historyMessages?.map((m, i) => (
                  <div
                    key={m.id ?? i}
                    className={`flex flex-col gap-[var(--space-2)] ${m.role === "user" ? "items-end" : "items-start"}`}
                  >
                    <Kicker size="sm" tone="faint">
                      {m.role === "user" ? t("chat.you") : t("chat.ai")}
                    </Kicker>
                    <ChatBubbleContent
                      content={m.content}
                      messageId={m.id}
                      role={m.role}
                      panelResultMessageId={analysisResult?.messageId}
                    />
                  </div>
                ))}

                {/* The live execution trace, so a physician can tell the
                    system has not died mid-analysis. Runs alongside any
                    stored traces from earlier turns in the same thread,
                    which historyMessages above already render (via
                    ChatBubbleContent) with running={false}. */}
                {sendMutation.isPending && <AgentTrace steps={trace} running />}

                {sendMutation.isPending && streamingText && (
                  <div className="flex flex-col items-start gap-[var(--space-2)]">
                    <Kicker size="sm" tone="faint">{t("chat.ai")}</Kicker>
                    <div
                      className="w-full whitespace-pre-wrap text-[15px] leading-[1.65]"
                      style={{ textAlign: "start" }}
                    >
                      {streamingText}
                      {/* Neutral, not accent: the signal colour is spent on
                          the privacy warning (the design restricts it to
                          a named short list) and the agent trace's own pulse
                          already owns "something is moving" here. */}
                      <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-neutral-900" />
                    </div>
                  </div>
                )}

                {zipFolder && <ZipDownloadBox folderName={zipFolder} />}

                {streamError && (
                  neutralNoticeKey ? (
                    <ErrorCard tone="notice" detail={t(neutralNoticeKey)} />
                  ) : (
                    <ErrorCard
                      detail={resolveStreamErrorText(streamError, t)}
                      onRetry={handleRetry}
                    />
                  )
                )}

                <div ref={bottomRef} />
              </>
            )}
          </div>
        </div>

        {analysisResult && (
          <ResultPanelShell>
            <ResultCard
              intent="analysis"
              data={analysisResult.data}
              folder={analysisResult.folder}
            />
          </ResultPanelShell>
        )}
      </div>

      {uploadError && (
        <div className="mx-auto w-full max-w-[1240px] px-[var(--space-6)] pt-[var(--space-2)]">
          <ErrorCard detail={uploadError} />
        </div>
      )}

      <Composer
        value={text}
        onChange={setText}
        onSubmit={() => handleSend()}
        onAbort={abort}
        pending={sendMutation.isPending}
        attachedPath={attachedFilePath}
        onAttach={(path) => {
          setUploadError(null);
          setAttachedFilePath(path);
        }}
        onAttachError={setUploadError}
        maxWidth={1240}
      />
    </div>
  );
}
