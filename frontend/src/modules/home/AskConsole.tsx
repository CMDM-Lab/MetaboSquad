"use client";

import { useState } from "react";
import { useT } from "@/src/i18n/LocaleContext";
import FileUpload from "@/src/modules/chatpage/UploadFlie";

// Positional mapping: chat.suggest1..3 line up with the analysis / id_mapping / plot_review
// intents the backend already names. Clicking a suggestion fills the
// composer with its exact wording and records the matching intent; typing
// clears the recorded intent again because the text is no longer the
// suggestion verbatim.
const SUGGESTION_INTENTS = ["analysis", "id_mapping", "plot_review"] as const;

export type AskConsoleProps = {
  /** Called with the composer text and the suggestion's intent, or null when the visitor typed their own words. */
  onSubmit: (text: string, intent: string | null) => void;
  pending: boolean;
  attachedFilePath: string | null;
  onAttachSuccess: (path: string) => void;
  onAttachError: (detail: string) => void;
};

// The natural-language console: deliberately the loudest element on the page
// (2px ink border on white) because it is the whole
// interaction model — a visitor who cannot find where to type has no path
// in. It embeds the existing FileUpload uploader rather than a second one.
export default function AskConsole({
  onSubmit,
  pending,
  attachedFilePath,
  onAttachSuccess,
  onAttachError,
}: AskConsoleProps) {
  const { t } = useT();
  const [text, setText] = useState("");
  const [intent, setIntent] = useState<string | null>(null);

  const suggestions = SUGGESTION_INTENTS.map((suggestionIntent, i) => ({
    intent: suggestionIntent,
    label: t(`chat.suggest${i + 1}`),
  }));

  const submit = () => {
    if (!text.trim() || pending) return;
    onSubmit(text, intent);
  };

  return (
    <div
      data-testid="ask-console"
      className="mt-[var(--space-8)] bg-white p-[var(--space-6)]"
      style={{ border: "2px solid var(--color-text)" }}
    >
      <div className="mb-[var(--space-2)] flex flex-wrap items-baseline gap-[var(--space-3)]">
        {/* text-accent-600 here, not the usual accent-700, is a deliberate,
            bounded exception: the design sets this one kicker to
            `color:var(--color-accent)` (accent-600) while every other kicker
            uses accent-700. This is the page's emphasised block, and the
            brighter kicker is part of what makes it the loudest element. Do
            not "fix" this back to accent-700. */}
        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-accent-600">
          {t("home.askKicker")}
        </span>
        <span className="text-[13px] text-[color-mix(in_srgb,var(--color-text)_62%,transparent)]">
          {t("home.askHint")}
        </span>
      </div>

      <div className="mt-[var(--space-4)] flex items-stretch gap-[var(--space-3)]">
        <div role="group" aria-label={t("home.attach")} className="flex-none">
          <FileUpload
            onUploadSuccess={onAttachSuccess}
            currentFilePath={attachedFilePath}
            onUploadError={onAttachError}
          />
        </div>
        <input
          className="input min-h-[58px] flex-1 px-[var(--space-4)] text-[17px]"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setIntent(null);
          }}
          onKeyDown={(e) => {
            // Guards against submitting mid-IME composition — without this,
            // every Chinese sentence would send on the first character
            // selected in the candidate window.
            if (e.key === "Enter" && !e.nativeEvent.isComposing) submit();
          }}
          placeholder={t("home.askPlaceholder")}
          disabled={pending}
        />
        <button
          type="button"
          className="btn btn-primary flex-none px-[var(--space-6)] text-[15px]"
          onClick={submit}
          disabled={pending}
        >
          {t("chat.send")}
        </button>
      </div>

      <div className="mt-[var(--space-4)] flex flex-wrap items-baseline gap-x-[var(--space-4)] gap-y-[var(--space-2)] border-t border-divider pt-[var(--space-3)]">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-[color-mix(in_srgb,var(--color-text)_48%,transparent)]">
          {t("home.askTry")}
        </span>
        {suggestions.map((s) => (
          <a
            key={s.intent}
            href="#"
            className="text-[13.5px] underline"
            onClick={(e) => {
              e.preventDefault();
              setText(s.label);
              setIntent(s.intent);
            }}
          >
            {s.label}
          </a>
        ))}
      </div>
    </div>
  );
}
