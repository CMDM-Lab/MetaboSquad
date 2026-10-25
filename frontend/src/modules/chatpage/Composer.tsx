// The docked composer shared by the thread (`/chat/[id]`) and the welcome
// screen (`/chat`). `maxWidth` is the only thing that
// differs per caller (1240px in the thread, 900px on the welcome screen);
// everything else is identical, so extracting this once keeps the two
// screens from drifting apart the way the old ChatWindow/Content duplication
// did.
//
// This component intentionally does not implement the double-submit guard
// or the abort logic itself — both already exist in ChatWindow.tsx
// (`sendGuardRef`, `useChatStream().abort`) and are passed in as `onSubmit` /
// `onAbort`. Reimplementing either here would give the thread two competing
// copies of the same guard.
//
// `onAbort` is optional: the welcome screen (`/chat`, Content.tsx) has no
// stream to abort before a thread even exists, so it has nothing meaningful
// to pass. When `onAbort` is absent, the pending state renders a disabled
// button instead of an abort affordance — never a button whose click does
// nothing.

"use client";

import { useT } from "@/src/i18n/LocaleContext";
import FileUpload from "./UploadFlie";

export type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onAbort?: () => void;
  pending: boolean;
  attachedPath: string | null;
  onAttach: (path: string) => void;
  onAttachError: (detail: string) => void;
  /** Pixels. 1240 in the thread, 900 on the welcome screen. */
  maxWidth: number;
};

export default function Composer({
  value,
  onChange,
  onSubmit,
  onAbort,
  pending,
  attachedPath,
  onAttach,
  onAttachError,
  maxWidth,
}: ComposerProps) {
  const { t } = useT();

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Guards against submitting mid-IME-composition — without this, every
    // Chinese sentence would send on the first character selected in the
    // candidate window (mirrors AskConsole.tsx's identical guard).
    if (e.key === "Enter" && !e.nativeEvent.isComposing) onSubmit();
  };

  return (
    <div className="shrink-0 border-t border-divider bg-[color-mix(in_srgb,white_30%,transparent)] px-[var(--space-6)] py-[var(--space-3)]">
      <div
        className="mx-auto flex items-center gap-[var(--space-2)]"
        style={{ maxWidth: `${maxWidth}px` }}
      >
        <FileUpload
          onUploadSuccess={onAttach}
          currentFilePath={attachedPath}
          onUploadError={onAttachError}
        />
        <input
          className="input flex-1"
          placeholder={t("chat.inputPlaceholder")}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={pending}
        />
        {pending && onAbort ? (
          // The visible label stays chat.sending (a "Generating…" ellipsis
          // label), but clicking this button aborts, not
          // sends — nothing else on screen tells a physician or a
          // screen-reader user that. The accessible name (chat.stop) carries
          // that meaning without changing what's printed on the button.
          <button
            type="button"
            onClick={onAbort}
            className="btn btn-primary whitespace-nowrap"
            aria-label={t("chat.stop")}
            title={t("chat.stop")}
          >
            {t("chat.sending")}
          </button>
        ) : pending ? (
          // No `onAbort` was passed (the welcome screen, before a thread
          // exists) — there is nothing to abort, so this renders as a
          // disabled status indicator rather than a button that looks
          // actionable but silently does nothing on click.
          <button type="button" className="btn btn-primary whitespace-nowrap" disabled>
            {t("chat.sending")}
          </button>
        ) : (
          <button type="button" onClick={onSubmit} className="btn btn-primary whitespace-nowrap">
            {t("chat.send")}
          </button>
        )}
      </div>
    </div>
  );
}
