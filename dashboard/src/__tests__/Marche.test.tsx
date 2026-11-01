import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Marche from "../pages/Marche";

// jsdom n'a pas de canvas : on mocke lightweight-charts (comme App.test.tsx)
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 0 },
  CandlestickSeries: {},
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

function sseBody(chunks: string[], delayMs = 0): ReadableStream<Uint8Array> {
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

const QUOTES_V1 = {
  quotes: [
    {
      symbol: "AAPL",
      value: 344.63,
      currency: "USD",
      source: "finnhub",
      timestamp: "2026-11-01T13:00:00+00:00",
      delayed: false,
    },
    {
      symbol: "SAP.DE",
      value: 211.25,
      currency: "EUR",
      source: "yahoo",
      timestamp: "2026-11-01T13:00:00+00:00",
      delayed: true,
    },
    {
      symbol: "BTC-USD",
      value: 69245,
      currency: "USD",
      source: "coingecko",
      timestamp: "2026-11-01T13:00:00+00:00",
      delayed: false,
    },
  ],
};

const QUOTES_V2 = {
  quotes: [
    {
      symbol: "AAPL",
      value: 345.5,
      currency: "USD",
      source: "finnhub",
      timestamp: "2026-11-01T13:05:00+00:00",
      delayed: false,
    },
  ],
};

describe("Page Marché (flux SSE live)", () => {
  it("affiche les prix reçus par le stream avec source et badge différé, puis les met à jour", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: sseBody(
          [
            `event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`,
            `event: quotes\ndata: ${JSON.stringify(QUOTES_V2)}\n\n`,
          ],
          100,
        ),
      }),
    );
    render(<Marche />);

    // Premier push : les 3 symboles avec prix, source, badge différé
    expect(await screen.findByText("344,63")).toBeInTheDocument();
    expect(screen.getByText("211,25")).toBeInTheDocument();
    expect(screen.getByText(/finnhub/)).toBeInTheDocument();
    expect(screen.getByText(/différé/i)).toBeInTheDocument();

    // Deuxième push : le prix AAPL se met à jour
    await waitFor(() =>
      expect(screen.getByText("345,50")).toBeInTheDocument(),
    );

    // Le GET part bien vers /market/stream avec les symboles
    const fetchMock = vi.mocked(fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/market/stream");
    expect(url).toContain("symbols=AAPL%2CSAP.DE%2CBTC-USD");
    expect(init.method ?? "GET").toBe("GET");
  });

  it("signale que le flux s'est arrêté quand le serveur le ferme", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: sseBody([`event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`]),
      }),
    );
    render(<Marche />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/flux.*interrompu/i);
    // Les derniers prix reçus restent affichés
    expect(screen.getByText("344,63")).toBeInTheDocument();
  });

  it("affiche une erreur lisible si le flux est indisponible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, body: null }),
    );
    render(<Marche />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Flux indisponible (HTTP 503)",
    );
  });
});
