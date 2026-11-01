import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

// La page Marché ouvre un flux SSE au montage : on stubbe fetch (API non dispo en test).
afterEach(() => {
  vi.unstubAllGlobals();
});
vi.stubGlobal(
  "fetch",
  vi.fn().mockResolvedValue({ ok: false, status: 503, body: null }),
);

// jsdom n'a pas de canvas : on mocke lightweight-charts (le vrai rendu est testé en E2E plus tard)
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 0 },
  CandlestickSeries: {},
}));

describe("App (layout + navigation)", () => {
  it("affiche les 4 pages dans la nav et le bandeau simulation", async () => {
    render(<App />);
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

  it("affiche la page marché par défaut avec le graphique", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: /marché/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /graphique fictif de/i })).toBeInTheDocument();
  });
});
