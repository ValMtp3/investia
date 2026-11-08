import { QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Traces from "../pages/Traces";
import { jsonResponse, newTestQueryClient } from "./fakeBackend";

// jsdom n'a pas de canvas : on mocke lightweight-charts et on espionne setData
const { setDataCalls, createChart } = vi.hoisted(() => {
  const setDataCalls: { options: unknown; points: unknown }[] = [];
  const createChart = vi.fn(() => ({
    addSeries: (_seriesType: unknown, options: unknown) => ({
      setData: (points: unknown) => setDataCalls.push({ options, points }),
    }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }));
  return { setDataCalls, createChart };
});
vi.mock("lightweight-charts", () => ({
  createChart,
  ColorType: { Solid: 0 },
  LineSeries: {},
}));

afterEach(() => {
  vi.unstubAllGlobals();
  setDataCalls.length = 0;
  createChart.mockClear();
});

const RUN_A = {
  id: "11111111-1111-1111-1111-111111111111",
  question: "prix AAPL ?",
  status: "ok",
  model: "gpt-6-luna",
  turns: 2,
  total_cost_cents: 0.03,
  created_at: "2026-11-05T10:00:00+00:00",
};
const RUN_B = {
  id: "22222222-2222-2222-2222-222222222222",
  question: "SAP.DE en hausse ?",
  status: "blocked",
  model: "elephant",
  turns: 3,
  total_cost_cents: 0,
  created_at: "2026-11-04T09:30:00+00:00",
};

// Spans OTel (étape 9) renvoyés par GET /traces/<id> : name/start_ts/end_ts/attributes/status/error.
const SPANS_A = [
  {
    name: "gen_ai.chat",
    start_ts: "2026-11-05T10:00:01+00:00",
    end_ts: "2026-11-05T10:00:03+00:00",
    attributes: {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "gpt-6-luna",
      "gen_ai.usage.input_tokens": 10,
    },
    status: "OK",
    error: null,
  },
  {
    name: "tool.call",
    start_ts: "2026-11-05T10:00:02+00:00",
    end_ts: "2026-11-05T10:00:02.500+00:00",
    attributes: { "gen_ai.tool.name": "get_quote", "tool.ok": true },
    status: "OK",
    error: null,
  },
  {
    name: "gen_ai.chat",
    start_ts: "2026-11-05T10:00:04+00:00",
    end_ts: "2026-11-05T10:00:04.200+00:00",
    attributes: { "gen_ai.request.model": "gpt-6-luna" },
    status: "ERROR",
    error: "RuntimeError",
  },
];

const DETAIL_A = {
  run: { ...RUN_A, answer: "AAPL vaut 344.63 $ (source : finnhub)." },
  steps: [
    {
      turn: 1,
      kind: "llm_call",
      payload: { model: "gpt-6-luna", cost_cents: 0.01 },
      created_at: "2026-11-05T10:00:01+00:00",
    },
    {
      turn: 1,
      kind: "tool_call",
      payload: { name: "get_quote", ok: true },
      created_at: "2026-11-05T10:00:02+00:00",
    },
  ],
  spans: SPANS_A,
};

const EVALS = {
  runs: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      started_at: "2026-11-04T09:00:00+00:00",
      model: "gpt-6-luna",
      commit: "abc1234",
      mode: "mock",
      results: [
        { case_id: "q1", metric: "tool_used", score: 1 },
        { case_id: "q2", metric: "tool_used", score: 0 },
        { case_id: "q1", metric: "disclaimer", score: 1 },
      ],
    },
    {
      id: "44444444-4444-4444-4444-444444444444",
      started_at: "2026-11-05T09:00:00+00:00",
      model: "elephant",
      commit: "def5678",
      mode: "mock",
      results: [
        { case_id: "q1", metric: "tool_used", score: 1 },
        { case_id: "q1", metric: "disclaimer", score: 0.5 },
      ],
    },
  ],
};

type Handler = (url: URL) => unknown;

/** Remplace `fetch` : /traces (liste), /traces/<id> (détail), /evals. */
function stubFetch(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/traces") return handlers.list(url);
    if (url.pathname.startsWith("/traces/")) return handlers.detail(url);
    if (url.pathname === "/evals") return handlers.evals(url);
    throw new Error(`appel inattendu : ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderTracesAt(path: string) {
  const rootRoute = createRootRoute();
  const tracesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/traces",
    validateSearch: (search: Record<string, unknown>) => ({
      run: typeof search.run === "string" && search.run ? search.run : undefined,
    }),
    component: Traces,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([tracesRoute]),
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("Page Traces & evals", () => {
  it("affiche la liste des exécutions puis le détail au clic", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A, RUN_B] }),
      detail: (url) =>
        url.pathname.endsWith(RUN_A.id)
          ? jsonResponse(DETAIL_A)
          : jsonResponse({ detail: "run inconnu" }, 404),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt("/traces");

    // Liste : question, statut, coût lisibles
    const list = await screen.findByRole("list", { name: /exécutions/i });
    expect(list).toHaveTextContent("prix AAPL ?");
    expect(list).toHaveTextContent("SAP.DE en hausse ?");
    expect(list).toHaveTextContent(/0,03\s?c/);

    // Clic sur la première exécution → détail chargé et affiché
    await userEvent.click(screen.getByRole("button", { name: /prix AAPL/i }));
    const detail = await screen.findByRole("region", { name: /détail/i });
    expect(detail).toHaveTextContent("AAPL vaut 344.63 $ (source : finnhub).");
    expect(detail).toHaveTextContent("llm_call");
    expect(detail).toHaveTextContent("get_quote");
    expect(detail).toHaveTextContent(/2 tours/);
  });

  it("présélectionne le run passé en ?run=<id>", async () => {
    const fetchMock = stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse(DETAIL_A),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt(`/traces?run=${RUN_A.id}`);
    // Le détail du run présélectionné s'affiche sans clic
    expect(await screen.findByText(/AAPL vaut 344\.63/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.map(([input]) => new URL(String(input)).pathname),
    ).toContain(`/traces/${RUN_A.id}`);
  });

  it("affiche un état vide explicite quand il n'y a aucune exécution", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [] }),
      detail: () => jsonResponse({ detail: "run inconnu" }, 404),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt("/traces");
    expect(await screen.findByText(/aucune exécution/i)).toBeInTheDocument();
    expect(await screen.findByText(/aucune évaluation/i)).toBeInTheDocument();
  });

  it("affiche une erreur lisible si l'API tombe", async () => {
    stubFetch({
      list: () => jsonResponse(null, 500),
      detail: () => jsonResponse({ detail: "run inconnu" }, 404),
      evals: () => jsonResponse(null, 500),
    });
    renderTracesAt("/traces");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => /500/.test(a.textContent ?? ""))).toBe(true);
  });

  it("affiche un message clair si le run demandé est inconnu (404)", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse({ detail: "run inconnu : xyz" }, 404),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt(`/traces?run=${RUN_B.id}`);
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => /run inconnu/i.test(a.textContent ?? ""))).toBe(true);
  });

  it("trace une courbe par métrique d'eval (moyenne par run, ordre chrono)", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse(DETAIL_A),
      evals: () => jsonResponse(EVALS),
    });
    renderTracesAt("/traces");

    // Légende : une entrée par métrique
    const legend = await screen.findByRole("list", { name: /métriques/i });
    expect(legend).toHaveTextContent("tool_used");
    expect(legend).toHaveTextContent("disclaimer");

    // Graphique : 2 séries tracées, points en ordre chrono croissant
    await waitFor(() => expect(setDataCalls.length).toBe(2));
    const pointsPerSeries = setDataCalls.map(
      (c) => c.points as { time: number; value: number }[],
    );
    // tool_used : run 04/11 → moyenne (1+0)/2 = 0,5 ; run 05/11 → 1
    // disclaimer : run 04/11 → 1 ; run 05/11 → 0,5
    const values = pointsPerSeries
      .map((points) => points.map((p) => p.value))
      .flat()
      .sort((a, b) => a - b);
    expect(values).toEqual([0.5, 0.5, 1, 1]);
    for (const points of pointsPerSeries) {
      const times = points.map((p) => p.time);
      expect(times).toEqual([...times].sort((a, b) => a - b));
    }
    // Le graphique a un texte alternatif
    expect(screen.getByRole("img", { name: /scores des éval/i })).toBeInTheDocument();
  });

  it("affiche les statuts en badges colorés (ok / bloqué) dans la liste", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A, RUN_B] }),
      detail: () => jsonResponse(DETAIL_A),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt("/traces");
    const list = await screen.findByRole("list", { name: /exécutions/i });
    expect(list).toHaveTextContent("ok");
    expect(list).toHaveTextContent("bloqué");
  });

  it("affiche les spans OTel du run (chronologique, statut, erreur) — étape 9", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse(DETAIL_A),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt(`/traces?run=${RUN_A.id}`);
    const spansList = await screen.findByRole("list", { name: /spans otel/i });
    expect(spansList).toHaveTextContent("gen_ai.chat");
    expect(spansList).toHaveTextContent("tool.call");
    expect(spansList).toHaveTextContent("get_quote");
    expect(spansList).toHaveTextContent("gpt-6-luna");
    // Span en erreur : statut + type d'erreur visibles
    expect(spansList).toHaveTextContent("RuntimeError");
    // Durée affichée (2 s pour le 1er span chat)
    expect(spansList).toHaveTextContent(/2\s?s/);
  });

  it("tolère un détail sans champ spans (vieux backend) : aucun span, pas d'erreur", async () => {
    const { spans: _spans, ...detailSansSpans } = DETAIL_A;
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse(detailSansSpans),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt(`/traces?run=${RUN_A.id}`);
    expect(await screen.findByText(/aucun span/i)).toBeInTheDocument();
  });

  it("affiche un état vide explicite quand le run demandé est null (étape 7)", async () => {
    stubFetch({
      list: () => jsonResponse({ runs: [RUN_A] }),
      detail: () => jsonResponse({ run: null, steps: [] }),
      evals: () => jsonResponse({ runs: [] }),
    });
    renderTracesAt(`/traces?run=${RUN_A.id}`);
    expect(await screen.findByText("Exécution introuvable.")).toBeInTheDocument();
  });
});
