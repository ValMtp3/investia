import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import Portefeuille from "../pages/Portefeuille";
import type { Portfolio } from "../api";

const MOCK_PORTFOLIO: Portfolio = {
  cash: 6_900.0,
  positions: [
    {
      symbol: "AAPL",
      quantity: 10,
      avg_price: 308.34,
      price_eur: 308.34,
      value_eur: 3_083.4,
      source: "finnhub",
      price_timestamp: "2026-10-31T15:00:00+00:00",
    },
  ],
  positions_value: 3_083.4,
  total_value: 9_983.4,
  currency: "EUR",
};

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
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => MOCK_PORTFOLIO,
      }),
    );
    renderWithQueryClient(<Portefeuille />);
    await waitFor(() =>
      expect(screen.getByText(/9 983,40/)).toBeInTheDocument(),
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("affiche une erreur lisible si l'API est down", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );
    renderWithQueryClient(<Portefeuille />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/API indisponible/),
    );
  });
});
