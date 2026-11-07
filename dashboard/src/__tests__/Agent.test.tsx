import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import Agent from "../pages/Agent";
import { jsonResponse, newTestQueryClient } from "./fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** La page Agent utilise <Link to="/traces"> : il lui faut un routeur dans le test. */
async function renderAgent() {
  const rootRoute = createRootRoute();
  const agentRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/agent",
    component: Agent,
  });
  const tracesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/traces",
    validateSearch: (search: Record<string, unknown>) => ({
      run: typeof search.run === "string" && search.run ? search.run : undefined,
    }),
    component: () => <div>page traces</div>,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([agentRoute, tracesRoute]),
    history: createMemoryHistory({ initialEntries: ["/agent"] }),
  });
  await router.load();
  return render(
    <QueryClientProvider client={newTestQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function sseBody(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

const FULL_RUN = [
  'event: start\ndata: {"question":"prix AAPL ?","max_turns":8,"run_id":"run-abc-123"}\n\n',
  'event: llm_call\ndata: {"turn":1,"model":"gpt-6-luna","cost_cents":0.01,"tool_calls":["get_quote"]}\n\n',
  'event: tool_call\ndata: {"turn":1,"name":"get_quote","arguments":{"symbol":"AAPL"},"ok":true}\n\n',
  'event: guardrail\ndata: {"turn":2,"check":"format","ok":true,"detail":"ok"}\n\n',
  'event: answer\ndata: {"turn":2,"text":"AAPL vaut 344.63 $"}\n\n',
  'event: done\ndata: {"turns":2,"cost_cents":0.03,"status":"ok"}\n\n',
].join("");

const PORTFOLIO = {
  cash: 10_000,
  positions: [
    {
      symbol: "AAPL",
      quantity: 10,
      avg_price: 200,
      price_eur: 180,
      value_eur: 1_800,
      source: "finnhub",
      price_timestamp: "2026-11-05T10:00:00+00:00",
    },
  ],
  positions_value: 1_800,
  total_value: 11_800,
  currency: "EUR",
};

// Flux SSE avec une demande de validation : pas d'événement « approval » tant que
// le test n'a pas cliqué (comme en vrai, où le serveur attend la décision).
const APPROVAL_RUN = [
  'event: start\ndata: {"question":"achète 3 AAPL","max_turns":8,"run_id":"run-abc-123"}\n\n',
  'event: llm_call\ndata: {"turn":1,"model":"gpt-6-luna","cost_cents":0.01,"tool_calls":["simulate_order"]}\n\n',
  'event: approval_request\ndata: {"run_id":"run-abc-123","turn":1,"symbol":"AAPL","side":"buy","quantity":3}\n\n',
  'event: tool_call\ndata: {"turn":1,"name":"simulate_order","arguments":{"symbol":"AAPL","side":"buy","quantity":3},"ok":true}\n\n',
  'event: llm_call\ndata: {"turn":2,"model":"gpt-6-luna","cost_cents":0.02,"tool_calls":[]}\n\n',
  'event: answer\ndata: {"turn":2,"text":"Ordre exécuté."}\n\n',
  'event: done\ndata: {"turns":2,"cost_cents":0.03,"status":"ok"}\n\n',
].join("");

interface AgentFetchOpts {
  sse?: string[];
  status?: number; // statut de POST /agent/run (défaut 200)
  hangStart?: boolean; // flux SSE qui ne se termine jamais
  portfolioStatus?: number; // statut de GET /portfolio (défaut 200)
  portfolioBody?: unknown; // corps de GET /portfolio si 200 (défaut PORTFOLIO)
  approvalStatus?: number; // statut de POST /agent/runs/:id/approval (défaut 200)
}

/** fetch routé : GET /portfolio → JSON, POST /agent/run → flux SSE, POST approval → JSON. */
function stubAgentFetch(opts: AgentFetchOpts = {}) {
  const sse = opts.hangStart
    ? new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              'event: start\ndata: {"question":"q","max_turns":8}\n\n',
            ),
          );
          // flux qui ne se termine jamais : simule un run long
        },
      })
    : sseBody(opts.sse ?? [""]);
  const status = opts.status ?? 200;
  const portfolioStatus = opts.portfolioStatus ?? 200;
  const approvalStatus = opts.approvalStatus ?? 200;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/portfolio") {
      return portfolioStatus === 200
        ? jsonResponse(opts.portfolioBody ?? PORTFOLIO)
        : jsonResponse({ detail: "portefeuille indisponible" }, portfolioStatus);
    }
    if (url.pathname.startsWith("/agent/runs/") && url.pathname.endsWith("/approval")) {
      return approvalStatus === 200
        ? jsonResponse({ status: "ok", decision: JSON.parse(String(init?.body)).decision })
        : jsonResponse({ detail: "approbation indisponible" }, approvalStatus);
    }
    return { ok: status < 400, status, body: sse };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Retrouve l'appel POST /agent/run parmi les appels fetch (le 1er est souvent /portfolio). */
function agentRunCall(fetchMock: ReturnType<typeof vi.fn>) {
  const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/agent/run"));
  if (!call) throw new Error("aucun appel à /agent/run");
  return call as [string, RequestInit];
}

describe("Page Agent (chat streaming SSE)", () => {
  it("affiche les étapes en direct puis la réponse et le récap", async () => {
    const fetchMock = stubAgentFetch({ sse: [FULL_RUN] });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    // Étapes en direct (aria-live)
    const steps = await screen.findByLabelText(/étapes de l'agent/i);
    await waitFor(() => expect(steps).toHaveTextContent("get_quote"));
    expect(steps).toHaveTextContent(/garde-fou format/i);

    // Réponse finale + récap done
    expect(await screen.findByText("AAPL vaut 344.63 $")).toBeInTheDocument();
    expect(screen.getByText(/2 tours/)).toBeInTheDocument();
    expect(screen.getByText(/statut ok/i)).toBeInTheDocument();

    // Le POST part bien vers /agent/run avec la question
    const [url, init] = agentRunCall(fetchMock);
    expect(url).toContain("/agent/run");
    expect(JSON.parse(init.body as string)).toEqual({ question: "prix AAPL ?" });
  });

  it("affiche un lien « Voir la trace » vers /traces?run=<run_id> après un run tracé", async () => {
    stubAgentFetch({ sse: [FULL_RUN] });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    const link = await screen.findByRole("link", { name: /voir la trace/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/traces?run=run-abc-123"));
  });

  it("affiche une erreur lisible si le flux tombe", async () => {
    stubAgentFetch({ status: 503 });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Flux indisponible (HTTP 503)",
    );
    // Pas de bulle « agent » vide qui traîne après l'erreur
    expect(screen.queryByText("agent")).not.toBeInTheDocument();
  });

  it("coupe le flux en cours quand on quitte la page", async () => {
    const fetchMock = stubAgentFetch({ hangStart: true });
    const { unmount } = await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "question longue");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    await screen.findByRole("button", { name: /stop/i });

    const [, init] = agentRunCall(fetchMock);
    expect(init.signal?.aborted).toBe(false);
    unmount();
    expect(init.signal?.aborted).toBe(true);
  });

  it("le bouton Stop interrompt le flux en cours", async () => {
    stubAgentFetch({ hangStart: true });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "question longue");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    const stop = await screen.findByRole("button", { name: /stop/i });
    await userEvent.click(stop);
    expect(await screen.findByText(/interrompu/i)).toBeInTheDocument();
  });

  it("affiche le résumé du portefeuille simulé à côté du chat", async () => {
    stubAgentFetch({ sse: [FULL_RUN] });
    await renderAgent();

    const module = await screen.findByRole("region", { name: /portefeuille/i });
    expect(await within(module).findByText(/11.?800,00/)).toBeInTheDocument(); // valeur totale
    expect(within(module).getByText(/10.?000,00/)).toBeInTheDocument(); // cash
    // « 1 800,00 » sans confondre avec « 11 800,00 » (lookbehind)
    expect(within(module).getByText(/(?<!1)1.?800,00/)).toBeInTheDocument(); // positions
    expect(within(module).getByText("AAPL")).toBeInTheDocument();
  });

  it("le chat fonctionne même si /portfolio renvoie une erreur", async () => {
    stubAgentFetch({ sse: [FULL_RUN], portfolioStatus: 500 });
    await renderAgent();

    // Le module portefeuille affiche une erreur lisible…
    const module = await screen.findByRole("region", { name: /portefeuille/i });
    expect(await within(module).findByRole("alert")).toHaveTextContent(/portefeuille/i);
    // …mais le chat, lui, marche encore
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    expect(await screen.findByText("AAPL vaut 344.63 $")).toBeInTheDocument();
  });

  it("affiche une erreur lisible si /portfolio renvoie un payload malformé", async () => {
    stubAgentFetch({ sse: [FULL_RUN], portfolioBody: { detail: "inattendu" } });
    await renderAgent();

    const module = await screen.findByRole("region", { name: /portefeuille/i });
    expect(await within(module).findByRole("alert")).toHaveTextContent(/malformée/i);
    // Le chat continue de fonctionner
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    expect(await screen.findByText("AAPL vaut 344.63 $")).toBeInTheDocument();
  });
});

describe("Page Agent — validation humaine d'un ordre (5.1)", () => {
  it("affiche le bloc Valider/Refuser sur approval_request et Valider envoie approved", async () => {
    const fetchMock = stubAgentFetch({ sse: [APPROVAL_RUN] });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "achète 3 AAPL");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    // Le bloc de validation apparaît avec l'ordre proposé
    const bloc = await screen.findByRole("group", { name: /ordre proposé/i });
    expect(bloc).toHaveTextContent(/acheter 3 AAPL/i);

    await userEvent.click(screen.getByRole("button", { name: /valider/i }));

    // Le POST part vers /agent/runs/run-abc-123/approval avec approved
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("/agent/runs/run-abc-123/approval"),
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ decision: "approved" });
    });

    // Le bloc se fige avec la décision (l'événement approval du flux confirme)
    expect(await screen.findByText(/validé/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /valider/i })).not.toBeInTheDocument();
    // Le chat a continué jusqu'à la réponse finale
    expect(await screen.findByText("Ordre exécuté.")).toBeInTheDocument();
  });

  it("Refuser envoie refused", async () => {
    const fetchMock = stubAgentFetch({ sse: [APPROVAL_RUN] });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "achète 3 AAPL");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    await screen.findByRole("group", { name: /ordre proposé/i });
    await userEvent.click(screen.getByRole("button", { name: /refuser/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("/agent/runs/run-abc-123/approval"),
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ decision: "refused" });
    });
    expect(await screen.findByText(/refusé/i)).toBeInTheDocument();
  });

  it("si le POST d'approbation échoue, le bloc affiche une erreur et le chat continue", async () => {
    stubAgentFetch({ sse: [APPROVAL_RUN], approvalStatus: 500 });
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "achète 3 AAPL");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    const bloc = await screen.findByRole("group", { name: /ordre proposé/i });
    await userEvent.click(within(bloc).getByRole("button", { name: /valider/i }));

    // Erreur lisible dans le bloc, boutons encore cliquables (réessayer possible)
    expect(await within(bloc).findByRole("alert")).toHaveTextContent(/approbation/i);
    // Le flux SSE, lui, a continué jusqu'au bout
    expect(await screen.findByText("Ordre exécuté.")).toBeInTheDocument();
  });
});
