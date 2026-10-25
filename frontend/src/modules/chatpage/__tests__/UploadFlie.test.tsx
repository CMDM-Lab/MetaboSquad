import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { ApiError } from "@/src/lib/apiClient";
import { uploadFile } from "@/src/services/post";
import FileUpload from "../UploadFlie";

vi.mock("@/src/services/post", () => ({
  uploadFile: vi.fn(),
}));

const mockedUploadFile = vi.mocked(uploadFile);

function renderUpload(onUploadError = vi.fn()) {
  const onUploadSuccess = vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <LocaleProvider>
        <FileUpload
          onUploadSuccess={onUploadSuccess}
          currentFilePath={null}
          onUploadError={onUploadError}
        />
      </LocaleProvider>
    </QueryClientProvider>,
  );
  const input = utils.container.querySelector('input[type="file"]') as HTMLInputElement;
  return { ...utils, input, onUploadSuccess, onUploadError };
}

describe("FileUpload", () => {
  beforeEach(() => {
    mockedUploadFile.mockReset();
  });

  // F: if the implementation regresses to showing a generic "file upload
  // failed" message — whether for a format error, an explicit backend
  // error, or a dropped connection — all three of these tests must go red:
  // each one needs to see the specific reason, not the same blanket
  // sentence.

  it("shows the specific format error and does not call the upload API when an unsupported file format is selected", async () => {
    const onUploadError = vi.fn();
    const { input } = renderUpload(onUploadError);

    // Uses fireEvent rather than userEvent.upload: the input's
    // accept=".csv, image/*" makes user-event v14 filter out a
    // non-matching file at the browser layer, so onChange never fires —
    // but a real user can still bypass the browser's accept filtering via
    // drag-and-drop or an "all files" picker option, letting an
    // unsupported file actually reach onChange. This simulates exactly
    // that path.
    const file = new File(["hello"], "note.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onUploadError).toHaveBeenCalledWith("不支援的檔案格式，請上傳 CSV 或圖片");
    expect(onUploadError).not.toHaveBeenCalledWith("檔案上傳失敗");
    expect(mockedUploadFile).not.toHaveBeenCalled();
  });

  it('shows the backend\'s detail, not a generic "file upload failed", when the backend returns an explicit error (ApiError)', async () => {
    mockedUploadFile.mockRejectedValue(new ApiError(400, "只允許上傳 CSV 檔案"));
    const onUploadError = vi.fn();
    const { input } = renderUpload(onUploadError);

    const file = new File(["a,b"], "data.csv", { type: "text/csv" });
    await userEvent.upload(input, file);

    await waitFor(() => expect(onUploadError).toHaveBeenCalledWith("只允許上傳 CSV 檔案"));
    expect(onUploadError).not.toHaveBeenCalledWith("檔案上傳失敗");
  });

  // On a dropped connection, the fetch/API layer throws a TypeError
  // (which is also an instance of Error). An implementation using
  // `error instanceof Error ? error.message : ...` would show an English
  // technical string to the physician instead of routing through the
  // unified i18n "cannot connect" message.
  it('shows the i18n "cannot connect" message, not the raw English text or a generic message, on a dropped connection (a TypeError that isn\'t an ApiError)', async () => {
    mockedUploadFile.mockRejectedValue(new TypeError("Failed to fetch"));
    const onUploadError = vi.fn();
    const { input } = renderUpload(onUploadError);

    const file = new File(["a,b"], "data.csv", { type: "text/csv" });
    await userEvent.upload(input, file);

    await waitFor(() =>
      expect(onUploadError).toHaveBeenCalledWith("無法連線到伺服器，請確認網路後重試"),
    );
    expect(onUploadError).not.toHaveBeenCalledWith("Failed to fetch");
    expect(onUploadError).not.toHaveBeenCalledWith("檔案上傳失敗");
  });

  it("still calls onUploadSuccess with the file path when the upload succeeds", async () => {
    mockedUploadFile.mockResolvedValue({ message: "ok", file_path: "/uploads/csv/data.csv" });
    const { input, onUploadSuccess } = renderUpload();

    const file = new File(["a,b"], "data.csv", { type: "text/csv" });
    await userEvent.upload(input, file);

    await waitFor(() => expect(onUploadSuccess).toHaveBeenCalledWith("/uploads/csv/data.csv"));
  });
});
