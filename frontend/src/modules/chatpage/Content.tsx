// The chat welcome screen (`/chat`).
//
// The scope paragraph (chat.welcomeScope) is the highest-stakes copy in the
// app: the old "or just chat with you" wording was removed on purpose. The market already has enough chatbots; a page that
// invites chit-chat gets chit-chat, and then the backend's scope guardrail
// (supervisor.py's DIRECT_RESPONSE_SYSTEM) can only keep declining it, which
// is a worse experience than never inviting it. `Content.test.tsx` pins this
// decision — see its comments before touching this file's copy or markup.

"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { addChat } from "@/src/services/post";
import { chatQueryKeys } from "@/src/queryKeys/chat";
import { ApiError } from "@/src/lib/apiClient";
import { useT } from "@/src/i18n/LocaleContext";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import Hairline from "@/src/components/Hairline";
import Composer from "./Composer";

// Positional mapping, matching the identical pattern already established in
// modules/home/AskConsole.tsx: chat.suggest1..3 line up with the analysis /
// id_mapping / plot_review intents the backend already names. Clicking a
// suggestion fills the composer with its exact wording without submitting;
// typing afterwards clears the recorded intent because the text is no
// longer the suggestion verbatim.
const SUGGESTION_INTENTS = ["analysis", "id_mapping", "plot_review"] as const;
const ROMAN_NUMERALS = ["I", "II", "III"] as const;

export default function Content() {
  const [text, setText] = useState("");
  const [, setIntent] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useT();
  const queryClient = useQueryClient();
  const [attachedFilePath, setAttachedFilePath] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const { mutate: addChatMutate, isPending } = useMutation({
    mutationFn: (_variables: { msg: string; file?: string | null }) => addChat(),

    onSuccess: (data, variables) => {
      const { msg, file } = variables;
      let url = `/chat/${data.thread_id}?firstMsg=${encodeURIComponent(msg)}`;

      if (file) {
        url += `&firstImg=${encodeURIComponent(file)}`;
      }

      setCreateError(null);
      router.push(url);
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.list() });
    },
    // Only ApiError.detail is backend-supplied, display-ready text. Everything
    // else -- including the dropped-connection TypeError, which is also an
    // instance of Error -- falls back to the translated network message, so a
    // physician never sees an untranslated English string.
    onError: (error: unknown) => {
      setCreateError(error instanceof ApiError ? error.detail : t("error.network"));
    },
  });

  const handleSend = () => {
    if (!text.trim() || isPending) return;
    addChatMutate({ msg: text, file: attachedFilePath });
  };

  const suggestions = SUGGESTION_INTENTS.map((suggestionIntent, i) => ({
    intent: suggestionIntent,
    numeral: ROMAN_NUMERALS[i],
    label: t(`chat.suggest${i + 1}`),
  }));

  return (
    <div className="flex h-full flex-col bg-bg text-text">
      <div className="flex flex-1 items-center justify-center px-[var(--space-6)] py-[var(--space-8)]">
        <div className="mx-auto max-w-[64ch] text-center">
          <Kicker size="md">{t("chat.kicker")}</Kicker>
          <h2 className="my-[var(--space-3)] text-[28px] font-medium">
            {t("chat.welcomeTitle")}
          </h2>
          <p className="text-justify text-[13px] hyphens-auto text-[color-mix(in_srgb,var(--color-text)_78%,transparent)]">
            {t("chat.welcomeScope")}
          </p>
          <Hairline />
          <div className="grid gap-[var(--space-2)] text-left">
            {suggestions.map((s) => (
              <a
                key={s.intent}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  // Mirrors AskConsole's disabled-while-pending guard: a
                  // suggestion click must not be actionable while a chat is
                  // already being created.
                  if (isPending) return;
                  setText(s.label);
                  setIntent(s.intent);
                }}
                className="flex items-baseline gap-[var(--space-3)] border-b border-divider pb-[var(--space-2)] text-[13.5px] text-text no-underline hover:text-accent-700"
              >
                <span className="font-mono tabular-nums text-accent-600">{s.numeral}</span>
                <span>{s.label}</span>
              </a>
            ))}
          </div>
        </div>
      </div>

      {createError && (
        <div className="mx-auto w-full max-w-[900px] px-[var(--space-6)] pt-[var(--space-2)]">
          <ErrorCard detail={createError} />
        </div>
      )}

      <Composer
        value={text}
        onChange={(value) => {
          setText(value);
          setIntent(null);
        }}
        onSubmit={handleSend}
        pending={isPending}
        attachedPath={attachedFilePath}
        onAttach={(path) => {
          setCreateError(null);
          setAttachedFilePath(path);
        }}
        onAttachError={setCreateError}
        maxWidth={900}
      />
    </div>
  );
}
