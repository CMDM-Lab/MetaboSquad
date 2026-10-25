export type SseEvent = { event: string; data: unknown };

/**
 * Extracts every complete event from the stream buffer and returns the
 * not-yet-complete tail. The caller must prepend `rest` to the next chunk,
 * or an event split across chunks will be lost.
 */
export function parseSseChunks(buffer: string): { events: SseEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: SseEvent[] = [];

  for (const chunk of parts) {
    if (!chunk.trim()) continue;

    let event = "message";
    let raw: string | null = null;

    for (const line of chunk.split("\n")) {
      if (line.startsWith("event: ")) {
        event = line.slice("event: ".length).trim();
      } else if (line.startsWith("data: ")) {
        raw = line.slice("data: ".length);
      }
    }

    if (raw === null) continue;
    try {
      events.push({ event, data: JSON.parse(raw) });
    } catch {
      // data isn't valid JSON: skip this one entry rather than failing the whole batch
      console.warn("[sse] 略過無法解析的事件", { event, raw });
    }
  }

  return { events, rest };
}
