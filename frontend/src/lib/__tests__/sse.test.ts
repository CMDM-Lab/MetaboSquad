import { describe, expect, it } from "vitest";
import { parseSseChunks } from "../sse";

describe("parseSseChunks", () => {
  it("parses a single complete event", () => {
    const { events, rest } = parseSseChunks(
      'event: text\ndata: {"content":"hi"}\n\n');
    expect(events).toEqual([{ event: "text", data: { content: "hi" } }]);
    expect(rest).toBe("");
  });

  it("parses multiple events", () => {
    const { events } = parseSseChunks(
      'event: status\ndata: {"content":"a","seq":1}\n\n' +
      'event: status\ndata: {"content":"b","seq":2}\n\n');
    expect(events.map((e) => (e.data as any).seq)).toEqual([1, 2]);
  });

  it("keeps the incomplete tail for the next chunk to continue", () => {
    const { events, rest } = parseSseChunks(
      'event: text\ndata: {"content":"done"}\n\nevent: status\ndata: {"cont');
    expect(events).toHaveLength(1);
    expect(rest).toBe('event: status\ndata: {"cont');
  });

  it("parses correctly an event split across chunks once continued", () => {
    const first = parseSseChunks('event: status\ndata: {"con');
    expect(first.events).toHaveLength(0);

    const second = parseSseChunks(first.rest + 'tent":"x","seq":7}\n\n');
    expect(second.events).toEqual([
      { event: "status", data: { content: "x", seq: 7 } },
    ]);
  });

  it("defaults to \"message\" when there is no event line", () => {
    const { events } = parseSseChunks('data: {"content":"x"}\n\n');
    expect(events[0].event).toBe("message");
  });

  it("ignores the backend's keepalive comment lines", () => {
    // The backend sends ": keepalive" while a step is silent, so Cloudflare does not close the stream.
    const { events, rest } = parseSseChunks(
      ': keepalive\n\nevent: status\ndata: {"content":"a","seq":1}\n\n: keepalive\n\n');
    expect(events).toEqual([{ event: "status", data: { content: "a", seq: 1 } }]);
    expect(rest).toBe("");
  });

  it("skips an event whose data is not valid JSON rather than failing the whole batch", () => {
    const { events } = parseSseChunks(
      "event: text\ndata: not-json\n\n" +
      'event: text\ndata: {"content":"ok"}\n\n');
    expect(events).toEqual([{ event: "text", data: { content: "ok" } }]);
  });
});
