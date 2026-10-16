/**
 * fetch() cevabının akışını okuyan küçük bir Server-Sent Events (SSE) çözücü.
 * SSE: sunucunun tek bir HTTP bağlantısı üzerinden parça parça olay göndermesi;
 * sohbette EVA'nın cevabı kelime kelime böyle gelir.
 */

export interface SSEEvent {
  event: string;
  data: string;
}

export async function* readSSE(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseChunk(chunk);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseChunk(chunk: string): SSEEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}
