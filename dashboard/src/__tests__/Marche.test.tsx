import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Marche from "../pages/Marche";
import {
  callsTo,
  historyBody,
  jsonResponse,
  newTestQueryClient,
  silentStreamResponse,
  sseBody,
  streamResponse,
  stubBackend,
} from "./fakeBackend";

// jsdom n'a pas de canvas : on mocke lightweight-charts et on espionne les points reçus
const { setData } = vi.hoisted(() => ({ setData: vi.fn() }));
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 0 },
  LineSeries: {},
}));

beforeEach(() => {
  setData.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderMarche() {
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <Marche />
    </QueryClientProvider>,
  );
}

const AAPL_POINTS = [
  { time: "2026-10-30", value: 340.1 },
  { time: "2026-10-31", value: 344.63 },
];
const SAP_POINTS = [
  { time: "2026-10-30", value: 210.0 },
  { time: "2026-10-31", value: 211.25 },
];

/** Historique par symbole, comme le backend (route /market/history). */
function historyRoute(url: URL) {
  const symbol = url.searchParams.get("symbol");
  if (symbol === "SAP.DE") {
    return jsonResponse(historyBody("SAP.DE", "eodhd", "EUR", SAP_POINTS));
  }
  return jsonResponse(historyBody("AAPL", "yahoo", "USD", AAPL_POINTS));
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
    const fetchMock = stubBackend({
      stream: () =>
        streamResponse(
          sseBody(
            [
              `event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`,
              `event: quotes\ndata: ${JSON.stringify(QUOTES_V2)}\n\n`,
            ],
            100,
          ),
        ),
      history: historyRoute,
    });
    renderMarche();

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
    const [streamUrl] = callsTo(fetchMock, "/market/stream");
    expect(streamUrl.searchParams.get("symbols")).toBe("AAPL,SAP.DE,BTC-USD");
  });

  it("signale que le flux s'est arrêté quand le serveur ferme le flux", async () => {
    stubBackend({
      stream: () =>
        streamResponse(
          sseBody([`event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`]),
        ),
      history: historyRoute,
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(/flux.*interrompu/i);
    // Les derniers prix reçus restent affichés
    expect(screen.getByText("344,63")).toBeInTheDocument();
  });

  it("étiquette une dernière clôture (date, pas d'heure) quand le prix en direct manque", async () => {
    const closeQuote = {
      quotes: [
        {
          symbol: "SAP.DE",
          value: 189.4,
          currency: "EUR",
          source: "eodhd",
          // minuit UTC : afficher « 00:00 » serait mensonger, c'est une clôture
          timestamp: "2026-10-30T00:00:00+00:00",
          delayed: true,
          is_close: true,
        },
      ],
    };
    stubBackend({
      stream: () =>
        streamResponse(sseBody([`event: quotes\ndata: ${JSON.stringify(closeQuote)}\n\n`])),
      history: historyRoute,
    });
    renderMarche();

    expect(await screen.findByText("189,40")).toBeInTheDocument();
    const card = screen.getByRole("button", { name: /SAP\.DE/ });
    expect(card).toHaveTextContent("clôture du 30/10");
    expect(card).toHaveTextContent("eodhd");
    expect(card).not.toHaveTextContent("00:00");
  });

  it("garde l'heure pour un prix en direct normal", async () => {
    stubBackend({
      stream: () =>
        streamResponse(
          sseBody([`event: quotes\ndata: ${JSON.stringify(QUOTES_V2)}\n\n`]),
        ),
      history: historyRoute,
    });
    renderMarche();

    await screen.findByText("345,50");
    const card = screen.getByRole("button", { name: /AAPL/ });
    expect(card).not.toHaveTextContent(/clôture du/);
    expect(card).toHaveTextContent(/\d{2}:\d{2}/);
  });

  it("affiche une erreur lisible si le flux est indisponible", async () => {
    stubBackend({
      stream: () => ({ ok: false, status: 503, body: null }),
      history: historyRoute,
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Flux indisponible (HTTP 503)",
    );
  });
});

describe("Page Marché (graphique : vrais cours de clôture)", () => {
  it("trace la courbe de clôture du symbole avec sa source et sa devise", async () => {
    const fetchMock = stubBackend({ stream: silentStreamResponse, history: historyRoute });
    renderMarche();

    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(AAPL_POINTS));
    expect(
      screen.getByRole("img", {
        name: "Courbe des cours de clôture de AAPL, 30 jours, source yahoo",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/cours de clôture journaliers.*source : yahoo.*devise : USD/i),
    ).toBeInTheDocument();

    const [historyUrl] = callsTo(fetchMock, "/market/history");
    expect(historyUrl.searchParams.get("symbol")).toBe("AAPL");
    expect(historyUrl.searchParams.get("days")).toBe("30");
  });

  it("n'annonce plus de données mock", async () => {
    stubBackend({ stream: silentStreamResponse, history: historyRoute });
    renderMarche();
    await waitFor(() => expect(setData).toHaveBeenCalled());
    expect(screen.queryByText(/mock/i)).not.toBeInTheDocument();
  });

  it("change de courbe quand on choisit un autre symbole", async () => {
    const fetchMock = stubBackend({ stream: silentStreamResponse, history: historyRoute });
    renderMarche();
    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(AAPL_POINTS));

    await userEvent.click(screen.getByRole("button", { name: /SAP\.DE/ }));

    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(SAP_POINTS));
    expect(
      await screen.findByText(/source : eodhd.*devise : EUR/i),
    ).toBeInTheDocument();
    const symbols = callsTo(fetchMock, "/market/history").map((url) =>
      url.searchParams.get("symbol"),
    );
    expect(symbols).toEqual(["AAPL", "SAP.DE"]);
  });

  it("indique le chargement de l'historique", async () => {
    stubBackend({ stream: silentStreamResponse, history: () => new Promise(() => {}) });
    renderMarche();
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Chargement de l'historique…",
    );
    expect(setData).not.toHaveBeenCalled();
  });

  it("affiche l'erreur du backend, qui nomme la source", async () => {
    stubBackend({
      stream: silentStreamResponse,
      history: () =>
        jsonResponse({ detail: "eodhd: clé API manquante" }, 502),
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "eodhd: clé API manquante",
    );
    expect(setData).not.toHaveBeenCalled();
  });

  it("affiche un message lisible si la réponse d'erreur n'est pas du JSON", async () => {
    stubBackend({
      stream: silentStreamResponse,
      history: () => ({ ok: false, status: 500, json: async () => Promise.reject(new Error("pas du json")) }),
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Historique indisponible (HTTP 500)",
    );
  });

  it("dit qu'il n'y a pas d'historique plutôt que d'afficher un graphique vide", async () => {
    stubBackend({
      stream: silentStreamResponse,
      history: () => jsonResponse(historyBody("AAPL", "yahoo", "USD", [])),
    });
    renderMarche();
    expect(
      await screen.findByText("Aucun historique disponible pour ce symbole."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(setData).not.toHaveBeenCalled();
  });
});
