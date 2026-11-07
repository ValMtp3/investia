import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { historyBody, jsonResponse, newTestQueryClient, silentStreamResponse } from "./fakeBackend";

// jsdom n'a pas de canvas : on mocke lightweight-charts (le vrai rendu est testé en E2E plus tard)
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 0 },
  AreaSeries: {},
  LineSeries: {},
}));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname === "/market/stream") return silentStreamResponse();
      if (url.pathname === "/market/history") {
        return jsonResponse(
          historyBody("AAPL", "yahoo", "USD", [{ time: "2026-10-31", value: 344.63 }]),
        );
      }
      if (url.pathname === "/portfolio") {
        return jsonResponse({
          cash: 10_000,
          positions: [],
          positions_value: 0,
          total_value: 10_000,
          currency: "EUR",
          initial_capital: 10_000,
        });
      }
      throw new Error(`appel inattendu : ${url.pathname}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderApp() {
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <App />
    </QueryClientProvider>,
  );
}

describe("Accessibilité du layout (étape 7)", () => {
  it("a un lien « Aller au contenu » qui cible le contenu principal", async () => {
    renderApp();
    const skipLink = await screen.findByRole("link", { name: /aller au contenu/i });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    const main = document.getElementById("main-content");
    expect(main).not.toBeNull();
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("donne le focus au contenu principal au chargement de la page", async () => {
    renderApp();
    await screen.findByRole("heading", { name: /marché/i });
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute("id", "main-content"),
    );
  });

  it("ramène le focus dans le contenu après un clic sur un lien de navigation", async () => {
    const user = userEvent.setup();
    renderApp();
    const nav = await screen.findByRole("navigation", { name: /navigation principale/i });
    await user.click(await screen.findByRole("link", { name: "Portefeuille" }));
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute("id", "main-content"),
    );
    expect(nav).toBeInTheDocument();
  });

  it("a des liens de navigation d'au moins 44 px de haut (cibles tactiles)", async () => {
    renderApp();
    const nav = await screen.findByRole("navigation", { name: /navigation principale/i });
    for (const label of ["Marché", "Portefeuille", "Agent", "Traces & evals"]) {
      expect(within(nav).getByRole("link", { name: label })).toHaveClass("min-h-11");
    }
  });

  it("garde le bandeau simulation permanent", async () => {
    renderApp();
    expect(await screen.findByText(/Simulation — argent fictif/i)).toBeInTheDocument();
  });

  it("affiche l'attribution des fournisseurs de données", async () => {
    renderApp();
    expect(await screen.findByText(/CoinGecko/)).toBeInTheDocument();
  });
});
