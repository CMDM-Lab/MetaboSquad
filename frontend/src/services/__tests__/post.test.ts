import { describe, expect, it, vi, beforeEach } from "vitest";
import { ApiError } from "@/src/lib/apiClient";
import { uploadFile } from "../post";

// When a physician uploads data.CSV (uppercase extension) on Windows
// with Excel installed, the browser commonly reports the MIME type as
// application/vnd.ms-excel rather than text/csv. UploadFlie.tsx's local
// precheck already used `.toLowerCase()` once and let this file through,
// but if post.ts's check here were case-sensitive and didn't also accept
// this MIME type, it would reject the file again here, inconsistently with
// the local precheck, and steer the physician toward "cannot connect to
// server" — a message unrelated to what actually happened.
describe("uploadFile format check", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("still treats an uppercase .CSV extension with a non-text/csv MIME type as a valid CSV, not blocked by case", async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "ok", file_path: "/uploads/csv/data.csv" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", spy);

    const file = new File(["a,b"], "data.CSV", { type: "application/vnd.ms-excel" });
    await uploadFile({ file });

    expect(spy).toHaveBeenCalled();
    // A .csv extension (case-insensitive) always goes through the /api/uploads/csv endpoint.
    expect(String(spy.mock.calls[0][0])).toContain("/api/uploads/csv");
  });

  it("throws an ApiError (not a plain Error) for a genuinely unsupported format, so the caller can tell it apart from a dropped-connection error", async () => {
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);

    const file = new File(["hello"], "note.txt", { type: "text/plain" });

    await expect(uploadFile({ file })).rejects.toBeInstanceOf(ApiError);
    expect(spy).not.toHaveBeenCalled();
  });
});
