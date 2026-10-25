// File attach control shared by the home console and the thread composer.

"use client";

import { useRef, useState, useEffect } from 'react';
import { uploadFile } from '@/src/services/post';
import { useMutation } from '@tanstack/react-query';
import { FaTimes } from "react-icons/fa";
import { FiFileText } from "react-icons/fi";
import { ApiError } from "@/src/lib/apiClient";
import { useT } from "@/src/i18n/LocaleContext";

// Props this component accepts.
type FileUploadProps = {
  onUploadSuccess: (path: string) => void; // Called with the backend's file path on a successful upload.
  currentFilePath: string | null;          // The parent's current file path (lets it clear the preview remotely).
  onUploadError?: (detail: string) => void; // Called with the specific failure reason for the parent to display.
};

export default function FileUpload({ onUploadSuccess, currentFilePath, onUploadError }: FileUploadProps) {
  const { t } = useT();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null); // The file the user picked.
  const [previewUrl, setPreviewUrl] = useState<string | null>(null); // The image preview object URL.

  // When the parent clears its stored path, clear the local preview too.
  useEffect(() => {
    if (currentFilePath === null) {
      setSelectedFile(null);
      if (previewUrl) URL.revokeObjectURL(previewUrl); // Release the browser's object URL memory.
      setPreviewUrl(null);
      // Also clear the hidden input's value, or picking the same file again
      // would not fire a change event next time.
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [currentFilePath]);


  const { mutate: uploadMutate, isPending } = useMutation({
    mutationFn: ({ file }: { file: File }) => uploadFile({ file }),

    onSuccess: (data) => {
      console.log("Upload succeeded");
      // Pass the API's returned file_path up so the parent can update its attachedFilePath.
      if (data.file_path) {
        onUploadSuccess(data.file_path);
      }
    },

    onError: (error) => {
      setSelectedFile(null);
      setPreviewUrl(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      // Only the backend's explicit ApiError.detail is display-ready
      // Chinese; everything else (including the TypeError a dropped
      // connection throws, which is also an Error) falls back to the i18n
      // generic message rather than show a physician an untranslated
      // English technical string.
      onUploadError?.(error instanceof ApiError ? error.detail : t("error.network"));
    }
  });

  const handleButtonClick = () => {
    // Trigger the hidden input's own click.
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    console.log("File selection event fired");
    const file = e.target.files?.[0];
    if (!file) return;

    // Pre-check locally (the backend's uploads.py:33,61 only accepts CSV
    // and images) to avoid a round trip just to discover the format is
    // wrong, and to give a more specific error.
    const isImage = file.type.startsWith("image/");
    const isCsv = file.name.toLowerCase().endsWith(".csv");
    if (!isImage && !isCsv) {
      onUploadError?.(t("error.uploadFormat"));
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setSelectedFile(file); // Remember the file.

    // If it's an image, generate a temporary local URL to show a preview.
    if (file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    } else {
      setPreviewUrl(null); // Not an image (e.g. .csv): no preview to generate.
    }

    // Kick off the React Query mutation.
    uploadMutate({ file });
  };

  const clearFile = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="relative">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".csv, image/*"
        className="hidden" // The real input stays hidden; the visible control below drives it.
      />

      {!selectedFile ? (
        // The attach trigger is a `.btn-secondary`
        // text button at 13px with `padding-inline: 18.4px` — not an icon
        // button — so every call site (the home console via AskConsole,
        // the thread's Composer) gets the same chrome from this one place.
        <button
          type="button"
          onClick={handleButtonClick}
          disabled={isPending}
          className="btn btn-secondary whitespace-nowrap"
          style={{ fontSize: "13px", paddingInline: "18.4px" }}
        >
          {isPending ? "..." : t("chat.attach")}
        </button>
      ) : (
        <div className="flex items-center gap-[var(--space-2)] border border-divider bg-neutral-100 px-[var(--space-2)] py-[6px]">
          {previewUrl ? (
            <img src={previewUrl} alt="Preview" className="h-8 w-8 object-cover" />
          ) : (
            <FiFileText size={16} className="shrink-0 text-accent-700" />
          )}
          {/* Compact size label, mono like the rest of this design's
              file/duration figures. */}
          <span className="max-w-[120px] truncate font-mono text-[11px] tabular-nums">
            {(selectedFile.size / 1024).toFixed(0)}K
          </span>
          <button type="button" onClick={clearFile} className="btn btn-ghost">
            <FaTimes size={10} />
          </button>
        </div>
      )}
    </div>
  );
}
