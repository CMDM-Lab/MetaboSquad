"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addChat } from "@/src/services/post";
import { chatQueryKeys } from "@/src/queryKeys/chat";
import { ApiError } from "@/src/lib/apiClient";
import { useT } from "@/src/i18n/LocaleContext";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import Hairline from "@/src/components/Hairline";
import AskConsole from "./AskConsole";
import CapabilityLedger from "./CapabilityLedger";

export default function Content() {
  const router = useRouter();
  const { t } = useT();
  const queryClient = useQueryClient();
  const [attachedFilePath, setAttachedFilePath] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const { mutate: addChatMutate, isPending } = useMutation({
    mutationFn: (variables: { msg: string; file?: string | null }) => addChat(),

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
    // ApiError.detail is the only backend-supplied text safe to show verbatim.
    // Everything else — including the dropped-connection TypeError, which is
    // also an instance of Error — falls back to the translated network
    // message, so a physician never sees an untranslated English string.
    onError: (error: unknown) => {
      setCreateError(error instanceof ApiError ? error.detail : t("error.network"));
    },
  });

  // `intent` is accepted per AskConsole's interface (set when the text came
  // from a suggestion click, null when typed) but this flow does not yet
  // branch on it — the create-chat request and its URL stay exactly as
  // before this redesign.
  const handleSubmit = (text: string, intent: string | null) => {
    void intent;
    if (!text.trim() || isPending) return;
    addChatMutate({ msg: text, file: attachedFilePath });
  };

  return (
    <div className="mx-auto w-full max-w-[1180px] px-[var(--space-6)] pt-[var(--space-8)] pb-[var(--space-6)]">
      {/* Layout A. The design's optional photograph aside was reviewed and
          rejected: there is no
          lab photograph to show, and an empty grey plate reads worse than a
          single column. `homeCols` stays `minmax(0,1fr)` and no <aside>
          renders here. */}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-[var(--space-8)]">
        <section>
          <Kicker size="md">{t("home.kicker")}</Kicker>
          <Hairline ink />
          <h1 className="mb-[var(--space-2)] text-[clamp(30px,3.4vw,40px)] tracking-[-0.03em]">
            MetaboSquad
          </h1>
          <p className="mb-[var(--space-6)] font-mono text-[11px] leading-[1.5] tracking-[0.14em] text-[color-mix(in_srgb,var(--color-text)_72%,transparent)] uppercase">
            {t("home.sub")}
          </p>
          <p className="text-justify hyphens-auto">{t("home.lede")}</p>

          <AskConsole
            onSubmit={handleSubmit}
            pending={isPending}
            attachedFilePath={attachedFilePath}
            onAttachSuccess={(path) => {
              setCreateError(null);
              setAttachedFilePath(path);
            }}
            onAttachError={setCreateError}
          />
          {createError && (
            <div className="mt-[var(--space-3)]">
              <ErrorCard detail={createError} />
            </div>
          )}
        </section>
      </div>

      <Hairline ink />

      <CapabilityLedger />

      <section className="mt-[var(--space-8)] grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] items-center gap-[var(--space-6)] border border-divider p-[var(--space-6)]">
        <div>
          <h4 className="mb-[var(--space-2)]">{t("home.aboutStripTitle")}</h4>
          <p className="text-justify text-[13.5px] hyphens-auto text-[color-mix(in_srgb,var(--color-text)_76%,transparent)]">
            {t("home.aboutStripBody")}
          </p>
        </div>
        <div className="flex justify-end">
          <Link href="/about" className="btn btn-primary">
            {t("home.aboutStripCta")}
          </Link>
        </div>
      </section>
    </div>
  );
}
