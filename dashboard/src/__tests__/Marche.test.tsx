import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

// jsdom n'a pas de canvas : on mocke lightweight-charts et on espionne ses appels
const { setData, remove, createChart } = vi.hoisted(() => {
  const setData = vi.fn();
  const remove = vi.fn();
  const createChart = vi.fn(() => ({
    addSeries: () => ({ setData }),
    timeScale: () => ({ fitContent: () => {} }),
    remove,
  }));
  return { setData, remove, createChart };
});
vi.mock("lightweight-charts", () => ({
  createChart,
  ColorType: { Solid: 0 },
  LineSeries: {},
  AreaSeries: {},
}));

beforeEach(() => {
  setData.mockClear();
  remove.mockClear();
  createChart.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
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
const BTC_POINTS = [
  { time: "2026-10-30", value: 68_000 },
  { time: "2026-10-31", value: 69_245 },
];
// Cours constant : variation de +0,00 %.
const GENERIC_POINTS = [
  { time: "2026-10-30", value: 100 },
  { time: "2026-10-31", value: 100 },
];

const POINTS_BY_SYMBOL: Record<string, { time: string; value: number }[]> = {
  AAPL: AAPL_POINTS,
  "SAP.DE": SAP_POINTS,
  "BTC-USD": BTC_POINTS,
};

/** Historique par symbole, comme le backend (route /market/history). */
function historyRoute(url: URL) {
  const symbol = url.searchParams.get("symbol") ?? "AAPL";
  const points = POINTS_BY_SYMBOL[symbol] ?? GENERIC_POINTS;
  const source = symbol === "SAP.DE" ? "eodhd" : "yahoo";
  const currency = symbol === "SAP.DE" ? "EUR" : "USD";
  return jsonResponse(historyBody(symbol, source, currency, points));
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

    // Le GET part bien vers /market/stream avec toute la liste de suivi
    const [streamUrl] = callsTo(fetchMock, "/market/stream");
    expect(streamUrl.searchParams.get("symbols")).toBe(
      "AAPL,SAP.DE,BTC-USD,MSFT,NVDA,ETH-USD,AIR.PA",
    );
  });

  it("affiche la variation du jour en badge coloré et une sparkline par carte", async () => {
    // Flux qui envoie un push puis reste ouvert (comme en vrai) : badge « en direct ».
    const quotesThenHang = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(`event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`),
        );
      },
    });
    stubBackend({
      stream: () => streamResponse(quotesThenHang),
      history: historyRoute,
    });
    renderMarche();

    // AAPL : 340,10 → 344,63 = +1,33 % (calculée depuis l'historique, pas le flux)
    expect(await screen.findByText("+1,33 %")).toBeInTheDocument();
    // BTC-USD : 68 000 → 69 245 = +1,83 %
    expect(screen.getByText("+1,83 %")).toBeInTheDocument();
    // Une sparkline (svg) par symbole de la liste
    expect((await screen.findAllByRole("img", { name: /tendance de .* sur 1 m/ })).length).toBe(7);
    // Le flux a reçu des prix : badge « en direct »
    expect(await screen.findByText("Flux en direct")).toBeInTheDocument();
  });

  it("affiche « erreur » sur la carte d'un symbole dont le prix a échoué", async () => {
    const badQuote = { quotes: [{ symbol: "AAPL", error: "finnhub: indisponible" }] };
    stubBackend({
      stream: () => streamResponse(sseBody([`event: quotes\ndata: ${JSON.stringify(badQuote)}\n\n`])),
      history: historyRoute,
    });
    renderMarche();

    const card = await screen.findByRole("button", { name: /AAPL/ });
    expect(card).toHaveTextContent("erreur");
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

  it("affiche la bonne date de clôture même si le lecteur est à l'ouest de l'UTC", async () => {
    // minuit UTC du 30/10 = 17 h le 29/10 à Los Angeles : sans `timeZone: "UTC"`
    // dans formatAsOf, la carte afficherait « clôture du 29/10 ».
    vi.stubEnv("TZ", "America/Los_Angeles");
    const closeQuote = {
      quotes: [
        {
          symbol: "SAP.DE",
          value: 189.4,
          currency: "EUR",
          source: "eodhd",
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

    await screen.findByText("189,40");
    expect(screen.getByRole("button", { name: /SAP\.DE/ })).toHaveTextContent(
      "clôture du 30/10",
    );
  });

  it("affiche l'horodatage tel quel quand la date n'est pas valide", async () => {
    const badDate = {
      quotes: [
        {
          symbol: "AAPL",
          value: 344.63,
          currency: "USD",
          source: "finnhub",
          timestamp: "hier soir",
          delayed: false,
        },
      ],
    };
    stubBackend({
      stream: () =>
        streamResponse(sseBody([`event: quotes\ndata: ${JSON.stringify(badDate)}\n\n`])),
      history: historyRoute,
    });
    renderMarche();

    await screen.findByText("344,63");
    expect(screen.getByRole("button", { name: /AAPL/ })).toHaveTextContent("hier soir");
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
    // un seul graphique, tracé une seule fois
    expect(createChart).toHaveBeenCalledTimes(1);
    expect(setData).toHaveBeenCalledTimes(1);
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
    // Les 7 cartes ont demandé leur historique au montage ; le clic n'en redemande pas
    // (le cache TanStack Query sert SAP.DE déjà vu).
    expect(symbols).toEqual(["AAPL", "SAP.DE", "BTC-USD", "MSFT", "NVDA", "ETH-USD", "AIR.PA"]);
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

  it("affiche l'erreur tout de suite, sans attendre de nouvelles tentatives", async () => {
    // Client avec les réglages par défaut de TanStack Query (3 nouvelles tentatives,
    // 1 s, 2 s, 4 s) : une erreur du backend ne doit pas rester 7 s sur « Chargement ».
    const defaultClient = new QueryClient();
    stubBackend({
      stream: silentStreamResponse,
      history: () => jsonResponse({ detail: "eodhd: clé API manquante" }, 502),
    });
    render(
      <QueryClientProvider client={defaultClient}>
        <Marche />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("clé API manquante");
  });

  it("refuse une réponse dont les points sont absents", async () => {
    stubBackend({
      stream: silentStreamResponse,
      history: () =>
        jsonResponse({ symbol: "AAPL", source: "yahoo", currency: "USD", points: null }),
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(/illisible/i);
    expect(createChart).not.toHaveBeenCalled();
  });

  it("refuse des points dont les dates ne sont pas strictement croissantes", async () => {
    // lightweight-charts lève une exception sur ces données : on s'arrête avant.
    const doublon = [
      { time: "2026-10-31", value: 1 },
      { time: "2026-10-31", value: 2 },
    ];
    stubBackend({
      stream: silentStreamResponse,
      history: () => jsonResponse(historyBody("AAPL", "yahoo", "USD", doublon)),
    });
    renderMarche();
    expect(await screen.findByRole("alert")).toHaveTextContent(/illisible/i);
    expect(createChart).not.toHaveBeenCalled();
  });

  it("n'emporte pas la page si le graphique plante au tracé", async () => {
    setData.mockImplementationOnce(() => {
      throw new Error("Value is null");
    });
    stubBackend({ stream: silentStreamResponse, history: historyRoute });
    renderMarche();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Le graphique n'a pas pu être tracé",
    );
    expect(remove).toHaveBeenCalledTimes(1); // graphique libéré malgré l'échec
    expect(screen.getByRole("heading", { name: /marché/i })).toBeInTheDocument();
  });

  it("ne recrée pas le graphique quand un prix en direct arrive", async () => {
    stubBackend({
      stream: () =>
        streamResponse(
          sseBody(
            [
              `event: quotes\ndata: ${JSON.stringify(QUOTES_V1)}\n\n`,
              `event: quotes\ndata: ${JSON.stringify(QUOTES_V2)}\n\n`,
            ],
            50,
          ),
        ),
      history: historyRoute,
    });
    renderMarche();

    await waitFor(() => expect(setData).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("345,50")).toBeInTheDocument(); // 2e prix reçu
    expect(createChart).toHaveBeenCalledTimes(1);
    expect(setData).toHaveBeenCalledTimes(1);
  });

  it("libère le graphique au changement de symbole puis au démontage", async () => {
    stubBackend({ stream: silentStreamResponse, history: historyRoute });
    const { unmount } = renderMarche();
    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(AAPL_POINTS));
    expect(remove).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /SAP\.DE/ }));
    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(SAP_POINTS));
    expect(remove).toHaveBeenCalledTimes(1);

    unmount();
    expect(remove).toHaveBeenCalledTimes(2);
  });

  it("annule les requêtes en cours et recharge quand on change de période", async () => {
    const signals: Record<string, AbortSignal | null | undefined> = {};
    stubBackend({
      stream: silentStreamResponse,
      history: (url, signal) => {
        const key = `${url.searchParams.get("symbol")}:${url.searchParams.get("days")}`;
        signals[key] = signal;
        const days = url.searchParams.get("days");
        // Seule la période 90 j répond ; les autres restent en suspens.
        return days === "90"
          ? jsonResponse(historyBody("AAPL", "yahoo", "USD", AAPL_POINTS))
          : new Promise(() => {});
      },
    });
    renderMarche();
    await waitFor(() => expect(signals["AAPL:30"]).toBeDefined());
    expect(signals["AAPL:30"]?.aborted).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "3 m" }));

    // L'ancienne requête (30 j) est annulée, la nouvelle part en days=90
    await waitFor(() => expect(signals["AAPL:30"]?.aborted).toBe(true));
    await waitFor(() => expect(signals["AAPL:90"]).toBeDefined());
    await waitFor(() => expect(setData).toHaveBeenLastCalledWith(AAPL_POINTS));
    // Le graphique annonce la nouvelle période dans son texte alternatif
    expect(
      await screen.findByRole("img", {
        name: "Courbe des cours de clôture de AAPL, 90 jours, source yahoo",
      }),
    ).toBeInTheDocument();
  });
});
