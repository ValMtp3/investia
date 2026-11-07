// Client SSE (Server-Sent Events) écrit à la main — zéro dépendance (D41).
// EventSource du navigateur ne fait que du GET : ici on a besoin de POST (/agent/run),
// donc on lit le body du fetch avec un ReadableStream + un parser incrémental.

export interface SseEvent {
  event: string;
  data: string;
}

/** Parser incrémental : un bloc SSE peut arriver coupé entre deux chunks. */
export class SseParser {
  private buffer = "";

  push(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const events: SseEvent[] = [];
    let separator = this.buffer.indexOf("\n\n");
    while (separator !== -1) {
      const block = this.buffer.slice(0, separator);
      this.buffer = this.buffer.slice(separator + 2);
      const parsed = this.parseBlock(block);
      if (parsed !== null) events.push(parsed);
      separator = this.buffer.indexOf("\n\n");
    }
    return events;
  }

  private parseBlock(block: string): SseEvent | null {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        // Spec SSE : un seul espace optionnel après ':' est retiré.
        dataLines.push(line.slice("data:".length).replace(/^ /, ""));
      }
      // Les lignes commençant par ':' sont des commentaires (heartbeat) : ignorées.
    }
    if (dataLines.length === 0) return null;
    return { event, data: dataLines.join("\n") };
  }
}

export interface StreamSseOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  onEvent: (event: string, data: unknown) => void;
}

/**
 * Lit un flux SSE jusqu'à la fin (ou l'abort) et appelle `onEvent` pour chaque
 * événement, avec `data` déjà parsé en JSON quand c'est du JSON.
 */
export async function streamSse(
  url: string,
  options: StreamSseOptions,
): Promise<void> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body,
    signal: options.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Flux indisponible (HTTP ${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  // Annule le reader dès que le signal abort (bouton stop), même si fetch
  // ne propage pas l'abort jusqu'au read en attente.
  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };
  options.signal?.addEventListener("abort", abort, { once: true });
  const dispatch = (events: SseEvent[]) => {
    for (const { event, data } of events) {
      let parsed: unknown = data;
      try {
        parsed = JSON.parse(data);
      } catch {
        // data texte brut : on garde la chaîne
      }
      options.onEvent(event, parsed);
    }
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      dispatch(parser.push(decoder.decode(value, { stream: true })));
    }
    dispatch(parser.push(decoder.decode()));
  } finally {
    options.signal?.removeEventListener("abort", abort);
    reader.releaseLock();
  }
  if (options.signal?.aborted) {
    throw new DOMException("Flux interrompu (stop demandé)", "AbortError");
  }
}
