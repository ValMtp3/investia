// 23c : A2UI 1.0 — store de surfaces + rendu via le catalogue whitelisté.
// TDD : écrit avant src/a2ui.ts et src/components/A2UISurface.tsx.

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { newTestQueryClient } from "./fakeBackend";

// jsdom n'a pas de canvas : on mocke lightweight-charts (pattern Marche.test.tsx)
const { createChart } = vi.hoisted(() => ({
  createChart: vi.fn(() => ({
    addSeries: () => ({ setData: vi.fn() }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: vi.fn(),
  })),
}));
vi.mock("lightweight-charts", () => ({
  createChart,
  ColorType: { Solid: 0 },
  LineSeries: {},
  AreaSeries: {},
}));

import { A2UIStore, type A2UIMessage, type A2UISurfaceModel } from "../a2ui";
import A2UISurface, { A2UI_CATALOG } from "../components/A2UISurface";

// HistoryChart utilise useMarketHistory (TanStack Query) : il faut un provider.
function renderSurface(surface: A2UISurfaceModel) {
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <A2UISurface surface={surface} />
    </QueryClientProvider>,
  );
}

describe("A2UIStore (23c)", () => {
  it("applique handshake version, surfaceUpdate, beginRendering, deleteSurface", () => {
    const store = new A2UIStore();
    store.apply({ version: "1.0" } as A2UIMessage);
    expect(store.version).toBe("1.0");

    store.apply({
      surfaceUpdate: {
        surfaceId: "ui-c1",
        components: [{ id: "root-c1", type: "HistoryChart", props: { symbol: "AAPL", days: 90 } }],
      },
    } as A2UIMessage);
    store.apply({
      beginRendering: { surfaceId: "ui-c1", root: "root-c1", catalogId: "investia-v1" },
    } as A2UIMessage);

    const surfaces = store.list();
    expect(surfaces).toHaveLength(1);
    expect(surfaces[0].root).toBe("root-c1");
    expect(surfaces[0].catalogId).toBe("investia-v1");
    expect(surfaces[0].components["root-c1"].props).toEqual({ symbol: "AAPL", days: 90 });

    store.apply({ deleteSurface: { surfaceId: "ui-c1" } } as A2UIMessage);
    expect(store.list()).toHaveLength(0);
  });

  it("fusionne les composants d'une même surface (mise à jour incrémentale)", () => {
    const store = new A2UIStore();
    store.apply({
      surfaceUpdate: { surfaceId: "s", components: [{ id: "a", type: "HistoryChart", props: {} }] },
    } as A2UIMessage);
    store.apply({
      surfaceUpdate: { surfaceId: "s", components: [{ id: "b", type: "HistoryChart", props: {} }] },
    } as A2UIMessage);
    const surface = store.list()[0];
    expect(Object.keys(surface.components).sort()).toEqual(["a", "b"]);
  });
});

describe("A2UISurface (23c)", () => {
  it("rend un composant du catalogue whitelisté", () => {
    const store = new A2UIStore();
    store.apply({
      surfaceUpdate: {
        surfaceId: "ui-c1",
        components: [{ id: "root-c1", type: "HistoryChart", props: { symbol: "AAPL", days: 30 } }],
      },
    } as A2UIMessage);
    store.apply({
      beginRendering: { surfaceId: "ui-c1", root: "root-c1", catalogId: "investia-v1" },
    } as A2UIMessage);
    renderSurface(store.list()[0]);
    expect(screen.getByLabelText("Composant HistoryChart")).toBeInTheDocument();
  });

  it("ignore un composant inconnu du catalogue (sécurité, comme 21b)", () => {
    const store = new A2UIStore();
    store.apply({
      surfaceUpdate: {
        surfaceId: "ui-x",
        components: [{ id: "root-x", type: "ComposantInconnu", props: { html: "<b>x</b>" } }],
      },
    } as A2UIMessage);
    store.apply({
      beginRendering: { surfaceId: "ui-x", root: "root-x", catalogId: "investia-v1" },
    } as A2UIMessage);
    const { container } = renderSurface(store.list()[0]);
    expect(container.textContent).toBe("");
    expect(screen.queryByLabelText(/Composant/)).not.toBeInTheDocument();
  });

  it("le catalogue ne contient que des composants whitelistés", () => {
    expect(Object.keys(A2UI_CATALOG)).toEqual(["HistoryChart"]);
  });
});
