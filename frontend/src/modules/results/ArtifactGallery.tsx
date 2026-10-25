"use client";

import { API_BASE } from "@/src/config/constants";
import { useT } from "@/src/i18n/LocaleContext";
import type { ArtifactFile } from "@/src/types/results";

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * A flat manifest of every artifact in the folder — name, kind, size, and a
 * download link. The headline figure a physician actually looks at is
 * rendered separately by `AnalysisHighlights`'s own 16:9 box; this table's
 * job is letting them retrieve every produced file, image or not, not
 * previewing them.
 */
export default function ArtifactGallery({ files }: { files: ArtifactFile[] }) {
  const { t } = useT();

  if (!files || files.length === 0) {
    return <p className="text-[13px] text-neutral-500">{t("result.noFiles")}</p>;
  }

  return (
    // Scrolls sideways rather than squeezing at the 380px result-panel
    // floor — same convention as IdMappingTable and MarkdownReport's tables.
    <div className="overflow-x-auto">
      <table className="table" style={{ fontVariantNumeric: "tabular-nums" }}>
        <thead>
          <tr>
            <th>{t("result.colFile")}</th>
            <th>{t("result.colKind")}</th>
            <th style={{ textAlign: "right" }}>{t("result.colSize")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.path}>
              <td className="text-[13px]">{f.name}</td>
              <td>
                <span className="tag tag-neutral">{f.kind}</span>
              </td>
              <td style={{ textAlign: "right" }} className="text-[12px]">
                {humanSize(f.size)}
              </td>
              <td style={{ textAlign: "right" }}>
                <a
                  href={`${API_BASE}${f.path}`}
                  download
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[12px]"
                >
                  {t("result.download")}
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
