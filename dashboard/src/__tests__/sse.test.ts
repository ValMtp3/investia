import { afterEach, describe, expect, it, vi } from "vitest";
import { SseParser, streamSse } from "../lib/sse";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SseParser", () => {
  it("parse un bloc complet event + data", () => {
    const parser = new SseParser();
    const events = parser.push('event: start\ndata: {"question":"prix AAPL ?"}\n\n');
    expect(events).toEqual([
      { event: "start", data: '{"question":"prix AAPL ?"}' },
    ]);
  });

  it("parse plusieurs blocs dans un même chunk", () => {
    const parser = new SseParser();
    const events = parser.push(
      'event: llm_call\ndata: {"turn":1}\n\nevent: done\ndata: {"status":"ok"}\n\n',
    );
    expect(events.map((e) => e.event)).toEqual(["llm_call", "done"]);
  });

  it("garde le reste quand un bloc est coupé entre deux chunk", () => {
    const parser = new SseParser();
    expect(parser.push('event: answer\ndata: {"text":"demi')).toEqual([]);
    const events = parser.push(' réponse"}\n\n');
    expect(events).toEqual([{ event: "answer", data: '{"text":"demi réponse"}' }]);
  });

  it("ignore les commentaires (lignes ':') et met 'message' comme event par défaut", () => {
    const parser = new SseParser();
    const events = parser.push(': heartbeat\n\ndata: hello\n\n');
    expect(events).toEqual([{ event: "message", data: "hello" }]);
  });

  it("joint les lignes data multiples avec un saut de ligne", () => {
    const parser = new SseParser();
    const events = parser.push("event: x\ndata: ligne1\ndata: ligne2\n\n");
    expect(events).toEqual([{ event: "x", data: "ligne1\nligne2" }]);
  });
});

describe("streamSse", () => {
  function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
  }

  it("appelle onEvent dans l'ordre avec le JSON parsé, en POST avec body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: sseStream([
        'event: start\ndata: {"question":"q"}\n\n',
        'event: done\ndata: {"status":"ok"}\n\n',
      ]),
    });
    vi.stubGlobal("fetch", fetchMock);

    const received: Array<{ event: string; data: unknown }> = [];
    await streamSse("http://api/agent/run", {
      method: "POST",
      body: { question: "q" },
      onEvent: (event, data) => received.push({ event, data }),
    });

    expect(received).toEqual([
      { event: "start", data: { question: "q" } },
      { event: "done", data: { status: "ok" } },
    ]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/agent/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ question: "q" });
    expect((init.headers as Record<string, string>)["Accept"]).toBe(
      "text/event-stream",
    );
  });

  it("lève une erreur lisible si le flux est indisponible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, body: null }),
    );
    await expect(
      streamSse("http://api/market/stream", { onEvent: () => {} }),
    ).rejects.toThrow("Flux indisponible (HTTP 503)");
  });

  it("propage l'abort (bouton stop) via le signal", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: sseStream(['event: start\ndata: {}\n\n']),
      }),
    );
    const promise = streamSse("http://api/agent/run", {
      method: "POST",
      body: { question: "q" },
      signal: controller.signal,
      onEvent: () => controller.abort(),
    });
    await expect(promise).rejects.toThrow();
    expect(controller.signal.aborted).toBe(true);
  });
});
