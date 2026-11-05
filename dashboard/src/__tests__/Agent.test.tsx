import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import Agent from "../pages/Agent";

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
  return render(<RouterProvider router={router} />);
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

describe("Page Agent (chat streaming SSE)", () => {
  it("affiche les étapes en direct puis la réponse et le récap", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, body: sseBody([FULL_RUN]) }),
    );
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
    const fetchMock = vi.mocked(fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/agent/run");
    expect(JSON.parse(init.body as string)).toEqual({ question: "prix AAPL ?" });
  });

  it("affiche un lien « Voir la trace » vers /traces?run=<run_id> après un run tracé", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, body: sseBody([FULL_RUN]) }),
    );
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "prix AAPL ?");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));

    const link = await screen.findByRole("link", { name: /voir la trace/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/traces?run=run-abc-123"));
  });

  it("affiche une erreur lisible si le flux tombe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, body: null }),
    );
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
    const encoder = new TextEncoder();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode('event: start\ndata: {"question":"q","max_turns":8}\n\n'),
          );
          // flux qui ne se termine jamais : simule un run long
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "question longue");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    await screen.findByRole("button", { name: /stop/i });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.signal?.aborted).toBe(false);
    unmount();
    expect(init.signal?.aborted).toBe(true);
  });

  it("le bouton Stop interrompt le flux en cours", async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode('event: start\ndata: {"question":"q","max_turns":8}\n\n'),
            );
            // flux qui ne se termine jamais : simule un run long
          },
        }),
      }),
    );
    await renderAgent();
    await userEvent.type(screen.getByLabelText(/question/i), "question longue");
    await userEvent.click(screen.getByRole("button", { name: /envoyer/i }));
    const stop = await screen.findByRole("button", { name: /stop/i });
    await userEvent.click(stop);
    expect(await screen.findByText(/interrompu/i)).toBeInTheDocument();
  });
});
