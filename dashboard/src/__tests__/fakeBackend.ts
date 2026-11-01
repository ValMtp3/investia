// Faux backend pour les tests : répond selon la route appelée (flux de prix, historique).
import { QueryClient } from "@tanstack/react-query";
import { vi } from "vitest";

export function newTestQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

export function sseBody(chunks: string[], delayMs = 0): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      for (const [i, chunk] of chunks.entries()) {
        controller.enqueue(encoder.encode(chunk));
        if (delayMs > 0 && i < chunks.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
      }
      controller.close();
    },
  });
}

/** Flux qui reste ouvert sans rien envoyer (pas de message « flux interrompu »). */
export function silentStream(): ReadableStream<Uint8Array> {
  return new ReadableStream({ start() {} });
}

export function streamResponse(body: ReadableStream<Uint8Array>) {
  return { ok: true, status: 200, body };
}

/** Réponse du flux de prix qui reste ouverte sans rien envoyer. */
export function silentStreamResponse() {
  return streamResponse(silentStream());
}

export function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

export function historyBody(
  symbol: string,
  source: string,
  currency: string,
  points: { time: string; value: number }[],
) {
  return { symbol, source, currency, delayed: false, points };
}

interface Routes {
  stream: () => unknown;
  history: (url: URL, signal?: AbortSignal | null) => unknown;
}

/** Remplace `fetch` : chaque route du backend a sa réponse simulée. */
export function stubBackend(routes: Routes) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/market/stream") return routes.stream();
    if (url.pathname === "/market/history") return routes.history(url, init?.signal);
    throw new Error(`appel inattendu : ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** URLs appelées sur une route donnée, dans l'ordre. */
export function callsTo(fetchMock: ReturnType<typeof stubBackend>, path: string): URL[] {
  return fetchMock.mock.calls
    .map(([input]) => new URL(String(input)))
    .filter((url) => url.pathname === path);
}
