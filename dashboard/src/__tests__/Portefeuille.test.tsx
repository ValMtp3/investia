import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import Portefeuille from "../pages/Portefeuille";
import type { Portfolio } from "../api";
import { jsonResponse } from "./fakeBackend";

const MOCK_PORTFOLIO: Portfolio = {
  cash: 6_900.0,
  positions: [
    {
      symbol: "AAPL",
      quantity: 10,
      avg_price: 300,
      price_eur: 308.34,
      value_eur: 3_083.4,
      source: "finnhub",
      price_timestamp: "2026-10-31T15:00:00+00:00",
    },
  ],
  positions_value: 3_083.4,
  total_value: 9_983.4,
  currency: "EUR",
  initial_capital: 10_000,
};

const MOCK_ORDERS = {
  orders: [
    {
      id: "o1",
      symbol: "AAPL",
      side: "buy",
      quantity: 10,
      price: 308.34,
      fee: 30.83,
      status: "simulated",
      created_at: "2026-11-05T10:00:00+00:00",
    },
  ],
};

const MOCK_ADJUSTMENTS = {
  adjustments: [
    {
      id: "a1",
      amount: 10_000,
      reason: "capital initial",
      created_at: "2026-10-31T09:00:00+00:00",
    },
  ],
};

interface FetchOpts {
  portfolio?: unknown;
  portfolioStatus?: number;
  orders?: unknown;
  adjustments?: unknown;
}

/** fetch routé : /portfolio, /orders, /portfolio/adjustments. */
function stubFetch(opts: FetchOpts = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/portfolio") {
      return opts.portfolioStatus && opts.portfolioStatus >= 400
        ? { ok: false, status: opts.portfolioStatus }
        : jsonResponse(opts.portfolio ?? MOCK_PORTFOLIO);
    }
    if (url.pathname === "/orders") return jsonResponse(opts.orders ?? MOCK_ORDERS);
    if (url.pathname === "/portfolio/adjustments") {
      return jsonResponse(opts.adjustments ?? MOCK_ADJUSTMENTS);
    }
    throw new Error(`appel inattendu : ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Page Portefeuille", () => {
  it("affiche la valeur totale depuis l'API", async () => {
    stubFetch();
    renderWithQueryClient(<Portefeuille />);
    await waitFor(() => expect(screen.getByText(/9 983,40/)).toBeInTheDocument());
    // AAPL apparaît dans le tableau des positions et dans celui des ordres
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    // Montants du tableau au même format français que le haut de page
    // (3 083,40 € apparaît dans le bloc Valeur et dans la ligne AAPL du tableau)
    expect(screen.getAllByText(/3\s083,40\s€/)).toHaveLength(2);
    expect(screen.getAllByText(/308,34\s€/).length).toBeGreaterThan(0);
  });

  it("affiche une erreur lisible si l'API est down", async () => {
    stubFetch({ portfolioStatus: 503 });
    renderWithQueryClient(<Portefeuille />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/API indisponible/),
    );
  });

  it("affiche une erreur lisible si le payload portefeuille est malformé", async () => {
    stubFetch({ portfolio: { detail: "inattendu" } });
    renderWithQueryClient(<Portefeuille />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/malformée/i);
  });

  it("affiche la performance depuis le capital de départ (initial_capital)", async () => {
    stubFetch();
    renderWithQueryClient(<Portefeuille />);
    // 9 983,40 € pour 10 000 € de départ = -0,17 %
    expect(await screen.findByText("-0,17 %")).toBeInTheDocument();
    expect(screen.getByText(/-16,60\s€/)).toBeInTheDocument();
    expect(screen.getByText(/depuis le départ/i)).toBeInTheDocument();
  });

  it("affiche la plus-value latente de chaque position", async () => {
    stubFetch();
    renderWithQueryClient(<Portefeuille />);
    const positionsModule = await screen.findByRole("region", { name: /positions/i });
    // AAPL : 10 × 308,34 − 10 × 300,00 = +83,40 €, soit +2,78 %
    expect(await within(positionsModule).findByText(/\+2,78 %/)).toBeInTheDocument();
    expect(within(positionsModule).getByText("83,40 €")).toBeInTheDocument();
  });

  it("affiche la répartition cash / positions", async () => {
    stubFetch();
    renderWithQueryClient(<Portefeuille />);
    expect(
      await screen.findByRole("img", { name: /répartition.*cash 69,1 %.*positions 30,9 %/i }),
    ).toBeInTheDocument();
  });

  it("affiche l'historique des ordres simulés et des ajustements", async () => {
    stubFetch();
    renderWithQueryClient(<Portefeuille />);
    const ordersModule = await screen.findByRole("region", { name: /ordres simulés/i });
    expect(await within(ordersModule).findByText("achat")).toBeInTheDocument();
    expect(within(ordersModule).getByText("simulé")).toBeInTheDocument();
    expect(within(ordersModule).getByText(/30,83\s€/)).toBeInTheDocument();

    const adjustmentsModule = await screen.findByRole("region", {
      name: /ajustements de capital/i,
    });
    expect(await within(adjustmentsModule).findByText(/capital initial/)).toBeInTheDocument();
    expect(within(adjustmentsModule).getByText(/10 000,00\s€/)).toBeInTheDocument();
  });

  it("affiche des états vides quand il n'y a ni ordre ni ajustement ni position", async () => {
    stubFetch({
      portfolio: { ...MOCK_PORTFOLIO, positions: [], positions_value: 0 },
      orders: { orders: [] },
      adjustments: { adjustments: [] },
    });
    renderWithQueryClient(<Portefeuille />);
    expect(await screen.findByText("Aucune position pour l'instant.")).toBeInTheDocument();
    expect(screen.getByText("Aucun ordre simulé pour l'instant.")).toBeInTheDocument();
    expect(screen.getByText("Aucun ajustement pour l'instant.")).toBeInTheDocument();
  });

  it("signale une réponse d'ordres illisible sans casser la page", async () => {
    stubFetch({ orders: { orders: [{ id: 42 }] } });
    renderWithQueryClient(<Portefeuille />);
    const ordersModule = await screen.findByRole("region", { name: /ordres simulés/i });
    expect(await within(ordersModule).findByRole("alert")).toHaveTextContent(/illisible/i);
    // Le reste de la page vit toujours
    expect(screen.getByRole("heading", { name: /portefeuille/i })).toBeInTheDocument();
  });
});
