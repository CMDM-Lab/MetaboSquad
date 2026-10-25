"use client";

import { useT } from "@/src/i18n/LocaleContext";
import Kicker from "@/src/components/Kicker";

export type ErrorCardTone = "error" | "notice";

type Props = {
  detail: string;
  onRetry?: () => void;
  tone?: ErrorCardTone;
};

// tone="notice" is for the two backend states that are not failures — the
// user stopped the stream themselves, or the backend short-circuited a
// duplicate request. error.streamAborted and error.duplicateRequest are
// neutral notices, not red error cards, and get no retry button. Call sites
// decide when to pass tone="notice". Default tone is "error", so a caller
// that never passes `tone` gets the error appearance and behaviour.
export default function ErrorCard({ detail, onRetry, tone = "error" }: Props) {
  const { t } = useT();
  const isNotice = tone === "notice";
  const showRetry = !isNotice && Boolean(onRetry);

  return (
    <div
      role="alert"
      className={
        isNotice
          ? "border border-divider bg-neutral-100 p-[var(--space-4)]"
          : "border border-accent-300 bg-accent-100 p-[var(--space-4)]"
      }
    >
      <Kicker tone={isNotice ? "faint" : "accent"}>{t("error.kicker")}</Kicker>
      <p className="mt-[var(--space-2)]">{detail}</p>

      {showRetry && (
        <div className="mt-[var(--space-3)] flex gap-[var(--space-2)]">
          <button type="button" onClick={onRetry} className="btn btn-secondary">
            {t("error.retry")}
          </button>
        </div>
      )}
    </div>
  );
}
