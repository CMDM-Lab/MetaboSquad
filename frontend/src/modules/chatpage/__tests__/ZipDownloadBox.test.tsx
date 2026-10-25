import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import ZipDownloadBox from "../ZipDownloadBox";

function renderBox(folderName = "uploads/output/x") {
  return render(
    <LocaleProvider><ZipDownloadBox folderName={folderName} /></LocaleProvider>,
  );
}

describe("ZipDownloadBox", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("opens a new tab to download the zip on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ zip_url: "/api/uploads/download/x.zip" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    renderBox();
    await userEvent.click(screen.getByRole("button", { name: /下載/ }));

    await waitFor(() => expect(openSpy).toHaveBeenCalled());
    expect(openSpy.mock.calls[0][0]).toContain("/api/uploads/download/x.zip");
  });

  // On a dropped connection, the browser's `fetch` throws
  // `TypeError("Failed to fetch")`, which is also an instance of `Error`.
  // An implementation using `e.message` would show an untranslated English
  // technical string to a physician on the Chinese interface — the same
  // pitfall already fixed once in useChatStream.ts (see its streamError
  // catch branch). This closes the same gap for
  // ZipDownloadBox.
  it("shows the i18n \"cannot connect\" message, not the raw English text, on a dropped connection (fetch throws TypeError)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    renderBox();
    await userEvent.click(screen.getByRole("button", { name: /下載/ }));

    await waitFor(() =>
      expect(screen.getByText("無法連線到伺服器，請確認網路後重試")).toBeInTheDocument());
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });

  it("shows the backend's raw detail text when the backend returns an explicit error (ApiError)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "資料夾不存在" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    renderBox();
    await userEvent.click(screen.getByRole("button", { name: /下載/ }));

    await waitFor(() => expect(screen.getByText("資料夾不存在")).toBeInTheDocument());
  });
});
