import { describe, expect, it, vi, beforeEach } from "vitest";
import { apiFetch, ApiError } from "../apiClient";

describe("apiFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("prefixes a relative path with API_BASE", async () => {
    const spy = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);

    await apiFetch("/api/chat/");

    expect(spy.mock.calls[0][0]).toMatch(/^https?:\/\/[^/]+\/api\/chat\/$/);
  });

  it("throws an ApiError with status and detail on a non-2xx response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "請求格式錯誤" }), { status: 400 })
    ));

    await expect(apiFetch("/api/chat/")).rejects.toMatchObject({
      status: 400,
      detail: "請求格式錯誤",
    });
    await expect(apiFetch("/api/chat/")).rejects.toBeInstanceOf(ApiError);
  });

  it("falls back detail to the status text when the response is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("<html>500</html>", { status: 500 })
    ));

    await expect(apiFetch("/api/chat/")).rejects.toMatchObject({
      status: 500,
      detail: "HTTP 500",
    });
  });
});
