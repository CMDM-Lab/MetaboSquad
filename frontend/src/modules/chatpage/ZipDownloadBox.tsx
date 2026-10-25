// Downloads the zipped output folder produced by an analysis run.

"use client";

import { useState } from "react";
import { API_BASE } from "@/src/config/constants";
import { useT } from "@/src/i18n/LocaleContext";
import { ApiError, apiJson } from "@/src/lib/apiClient";

type ZipDownloadBoxProps = {
  /** The backend-generated analysis output folder name. */
  folderName: string;
};

export default function ZipDownloadBox({ folderName }: ZipDownloadBoxProps) {
  const { t } = useT();
  const [isZipping, setIsZipping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setIsZipping(true);
    setError(null);
    try {
      // Always goes through apiJson — never a bare fetch or a hardcoded host.
      const data = await apiJson<{ zip_url?: string }>("/api/uploads/download-zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_name: folderName }),
      });

      // window.open triggers the browser's native download of the ZIP.
      if (data?.zip_url) {
        window.open(`${API_BASE}${data.zip_url}`, "_blank");
      } else {
        setError(t("result.noFiles"));
      }
    } catch (e) {
      // No alert(): errors render in this component's own error state.
      // Only an ApiError's `detail` (an explicit backend response) is
      // human-facing Chinese; everything else falls back to the i18n
      // "cannot connect" string — most commonly the `TypeError("Failed to
      // fetch")` a dropped connection throws, which is still an `Error`
      // and would otherwise leak an untranslated English string to a
      // physician (same class of bug useChatStream.ts guards against for
      // its own stream; this closes the same gap here).
      setError(e instanceof ApiError ? e.detail : t("error.network"));
    } finally {
      setIsZipping(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        disabled={isZipping}
        onClick={handleDownload}
        className="btn btn-secondary disabled:opacity-50"
      >
        {isZipping ? t("result.zipping") : t("result.downloadZip")}
      </button>
      {error && <p className="mt-[var(--space-2)] text-[12px] text-accent-700">{error}</p>}
    </div>
  );
}
