import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  historyBody,
  jsonResponse,
  newTestQueryClient,
  silentStreamResponse,
  stubBackend,
} from "./fakeBackend";

// La page Marché ouvre un flux SSE et charge un historique au montage : faux backend (API non dispo en test).
beforeEach(() => {
  stubBackend({
    stream: silentStreamResponse,
    history: () =>
      jsonResponse(
        historyBody("AAPL", "yahoo", "USD", [{ time: "2026-10-31", value: 344.63 }]),
      ),
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

// jsdom n'a pas de canvas : on mocke lightweight-charts (le vrai rendu est testé en E2E plus tard)
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 0 },
  LineSeries: {},
  AreaSeries: {},
}));

function renderApp() {
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App (layout + navigation)", () => {
  it("affiche les 4 pages dans la nav et le bandeau simulation", async () => {
    renderApp();
    const nav = await screen.findByRole("navigation", {
      name: /navigation principale/i,
    });
    for (const label of ["Marché", "Portefeuille", "Agent", "Traces & evals"]) {
      expect(nav).toHaveTextContent(label);
    }
    expect(
      screen.getByText(/Simulation — argent fictif/i),
    ).toBeInTheDocument();
  });

  it("affiche la page marché par défaut avec le graphique des cours", async () => {
    renderApp();
    expect(
      await screen.findByRole("heading", { name: /marché/i }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("img", { name: /courbe des cours de clôture de AAPL/i }),
    ).toBeInTheDocument();
  });
});
