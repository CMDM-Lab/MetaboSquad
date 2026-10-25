"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE } from "@/src/config/constants";

/**
 * Every `.md` report the backend writes is rendered through here. Tables
 * must scroll horizontally rather than squeeze (the PubChem roll-up table
 * has 12 columns, the WCAG report has 5).
 */
export default function MarkdownReport({ markdown }: { markdown: string }) {
  return (
    <div className="space-y-3 text-[13px] leading-relaxed">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h1 className="mt-4 mb-2 text-lg font-medium" {...p} />,
          h2: (p) => <h2 className="mt-4 mb-2 text-base font-medium" {...p} />,
          h3: (p) => <h3 className="mt-3 mb-1 font-medium" {...p} />,
          p: (p) => <p className="my-2" {...p} />,
          ul: (p) => <ul className="my-2 list-disc space-y-1 pl-5" {...p} />,
          ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-5" {...p} />,
          blockquote: (p) => (
            <blockquote
              className="my-2 border-l-2 border-divider pl-3 text-neutral-500"
              {...p}
            />
          ),
          table: (p) => (
            <div className="my-3 overflow-x-auto">
              <table className="table" {...p} />
            </div>
          ),
          code: ({ children, className }) => {
            const isBlock = (className ?? "").includes("language-");
            if (isBlock) {
              return (
                <code className="block whitespace-pre overflow-x-auto bg-neutral-100 p-3 font-mono text-xs text-neutral-900">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-neutral-100 px-1 py-0.5 font-mono text-xs">
                {children}
              </code>
            );
          },
          pre: (p) => <pre className="my-3" {...p} />,
          a: ({ href, children }) => {
            // Report bodies link images/files with the backend's relative
            // `/uploads/...` path; the global `a` rule (globals.css) already
            // supplies the accent colour, so this override only resolves
            // the href, matching the same convention as the `img` override
            // below and ArtifactGallery/ZipDownloadBox.
            const resolved = href?.startsWith("/uploads/") ? `${API_BASE}${href}` : href;
            return (
              <a href={resolved} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
          img: ({ src, alt }) => {
            // Report bodies link images/files with the backend's relative
            // `/uploads/...` path; everywhere else that convention is
            // resolved against API_BASE the same way (ArtifactGallery,
            // ZipDownloadBox).
            const resolved =
              typeof src === "string" && src.startsWith("/uploads/")
                ? `${API_BASE}${src}`
                : src;
            return (
              <img
                src={resolved as string}
                alt={alt ?? ""}
                className="my-2 max-h-96 max-w-full border border-divider object-contain"
              />
            );
          },
        }}
      >
        {markdown}
      </Markdown>
    </div>
  );
}
