import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import {
  respondApproval,
  streamAgentRun,
  usePortfolio,
  type AgentEvent,
  type Portfolio,
} from "../api";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";
import { isAbortError } from "../lib/errors";
import { formatMoney } from "../lib/format";

interface Step {
  id: number;
  text: string;
  ok?: boolean;
}

/** Ordre proposé par l'agent, en attente de validation humaine (étape 5.1). */
interface PendingApproval {
  runId: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  decision?: string;
  error?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  text?: string;
  steps: Step[];
  answer?: string;
  summary?: string;
  stopped?: boolean;
  runId?: string | null;
  approval?: PendingApproval;
}

/** Garde-fou : le payload /portfolio doit avoir la forme attendue avant affichage. */
function isPortfolioPayload(data: Portfolio | undefined): data is Portfolio {
  return (
    data != null &&
    typeof data.total_value === "number" &&
    typeof data.cash === "number" &&
    typeof data.positions_value === "number" &&
    Array.isArray(data.positions)
  );
}

function stepText(event: AgentEvent): { text: string; ok?: boolean } | null {
  switch (event.kind) {
    case "llm_call": {
      const tools = event.payload.tool_calls.length
        ? ` → outils : ${event.payload.tool_calls.join(", ")}`
        : "";
      return { text: `Appel LLM · tour ${event.payload.turn} · ${event.payload.model}${tools}` };
    }
    case "tool_call":
      return {
        text: `Outil ${event.payload.name} (${JSON.stringify(event.payload.arguments)})`,
        ok: event.payload.ok,
      };
    case "guardrail":
      return {
        text: `Garde-fou ${event.payload.check} — ${
          event.payload.ok ? "ok" : `bloqué : ${event.payload.detail}`
        }`,
        ok: event.payload.ok,
      };
    default:
      return null;
  }
}

export default function Agent() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stepIdRef = useRef(0);
  // Résumé du portefeuille simulé (l'agent y a accès via l'outil get_portfolio).
  const portfolio = usePortfolio();

  // Quitter la page coupe le flux : sinon le run continue (et coûte des appels au modèle).
  useEffect(() => () => abortRef.current?.abort(), []);

  function patchLastAssistant(patch: (msg: ChatMessage) => ChatMessage) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "assistant") next[next.length - 1] = patch(last);
      return next;
    });
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || running) return;
    setInput("");
    setError(null);
    setRunning(true);
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question, steps: [] },
      { role: "assistant", steps: [] },
    ]);
    try {
      await streamAgentRun(
        question,
        (evt) => {
          const step = stepText(evt);
          if (step) {
            stepIdRef.current += 1;
            const id = stepIdRef.current;
            patchLastAssistant((msg) => ({
              ...msg,
              steps: [...msg.steps, { id, text: step.text, ok: step.ok }],
            }));
          } else if (evt.kind === "start") {
            // Le run est tracé côté backend : on garde son id pour le lien « voir la trace ».
            patchLastAssistant((msg) => ({ ...msg, runId: evt.payload.run_id ?? null }));
          } else if (evt.kind === "answer") {
            patchLastAssistant((msg) => ({ ...msg, answer: evt.payload.text }));
          } else if (evt.kind === "done") {
            patchLastAssistant((msg) => ({
              ...msg,
              summary: `Terminé en ${evt.payload.turns} tours · coût ${evt.payload.cost_cents} c · statut ${evt.payload.status}`,
            }));
          } else if (evt.kind === "approval_request") {
            // L'agent s'arrête : un ordre est proposé, à valider ou refuser (D57).
            patchLastAssistant((msg) => ({
              ...msg,
              approval: {
                runId: evt.payload.run_id,
                symbol: evt.payload.symbol,
                side: evt.payload.side,
                quantity: evt.payload.quantity,
              },
            }));
          } else if (evt.kind === "approval") {
            // La décision est confirmée côté serveur : on fige le bloc.
            patchLastAssistant((msg) =>
              msg.approval
                ? { ...msg, approval: { ...msg.approval, decision: evt.payload.decision } }
                : msg,
            );
          } else if (evt.kind === "error") {
            patchLastAssistant((msg) => ({
              ...msg,
              answer: `Erreur pendant le run : ${evt.payload.message}`,
            }));
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (isAbortError(err)) {
        patchLastAssistant((msg) => ({ ...msg, stopped: true }));
      } else {
        setError(err instanceof Error ? err.message : "Erreur inconnue");
        // Pas de bulle « agent » vide : l'erreur est déjà affichée au-dessus.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          const isEmptyAssistant =
            last?.role === "assistant" && last.steps.length === 0 && !last.answer;
          return isEmptyAssistant ? prev.slice(0, -1) : prev;
        });
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  /** Envoie la décision humaine au backend (D57) et met à jour le bloc. */
  async function decideApproval(runId: string, decision: "approved" | "refused") {
    const patch = (msg: ChatMessage): ChatMessage =>
      msg.approval && msg.approval.runId === runId
        ? { ...msg, approval: { ...msg.approval, decision, error: undefined } }
        : msg;
    try {
      await respondApproval(runId, decision);
      patchLastAssistant(patch);
    } catch (err) {
      // Le flux SSE continue quoi qu'il arrive : on signale juste l'échec du POST.
      patchLastAssistant((msg) =>
        msg.approval && msg.approval.runId === runId
          ? {
              ...msg,
              approval: {
                ...msg.approval,
                error: err instanceof Error ? err.message : "Erreur inconnue",
              },
            }
          : msg,
      );
    }
  }

  return (
    <section aria-labelledby="agent-title">
      <h1 id="agent-title" className="mb-3 text-lg font-medium">
        Conseils de l'agent
      </h1>

      <Module title="Portefeuille simulé" className="mb-3">
        {portfolio.isLoading && (
          <p role="status" className="text-muted">
            Chargement du portefeuille…
          </p>
        )}
        {portfolio.isError && (
          <ErrorNotice>
            Portefeuille indisponible :{" "}
            {portfolio.error instanceof Error ? portfolio.error.message : "API indisponible"}
          </ErrorNotice>
        )}
        {portfolio.data && !isPortfolioPayload(portfolio.data) && (
          <ErrorNotice>Portefeuille indisponible : réponse malformée.</ErrorNotice>
        )}
        {isPortfolioPayload(portfolio.data) && (
          <>
            <dl className="flex flex-wrap gap-x-6 gap-y-1">
              <div className="flex items-baseline gap-2">
                <dt className="text-muted">Valeur totale</dt>
                <dd className="font-medium">
                  {formatMoney(portfolio.data.total_value, portfolio.data.currency)}
                </dd>
              </div>
              <div className="flex items-baseline gap-2">
                <dt className="text-muted">Cash</dt>
                <dd>{formatMoney(portfolio.data.cash, portfolio.data.currency)}</dd>
              </div>
              <div className="flex items-baseline gap-2">
                <dt className="text-muted">Positions</dt>
                <dd>{formatMoney(portfolio.data.positions_value, portfolio.data.currency)}</dd>
              </div>
            </dl>
            {portfolio.data.positions.length > 0 && (
              <p className="mt-1 text-muted">
                {portfolio.data.positions.map((position) => position.symbol).join(", ")}
              </p>
            )}
          </>
        )}
      </Module>

      <Module title="Demande à l'agent" className="mb-3">
        <form onSubmit={send} className="flex gap-2">
          <div className="min-w-0 flex-1">
            <label htmlFor="agent-question" className="sr-only">
              Question
            </label>
            <input
              id="agent-question"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={2000}
              placeholder="ex. : prix de AAPL ?"
              className="w-full border border-rule bg-paper px-3 py-2 placeholder:text-muted"
            />
          </div>
          <button
            type="submit"
            disabled={running || !input.trim()}
            className="bg-ink px-4 py-2 font-medium text-paper hover:bg-signal disabled:opacity-50 disabled:hover:bg-ink"
          >
            Envoyer
          </button>
          {running && (
            <button
              type="button"
              onClick={stop}
              className="border border-signal px-4 py-2 font-medium text-signal-ink hover:bg-signal-wash"
            >
              Stop
            </button>
          )}
        </form>
      </Module>

      {running && (
        <p role="status" className="mb-3 text-muted">
          L'agent réfléchit…
        </p>
      )}
      {error && <ErrorNotice className="mb-3">{error}</ErrorNotice>}

      <ol className="space-y-3">
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <li key={i} className="border border-rule bg-wash p-3">
              <div className="text-xs font-medium text-muted">toi</div>
              <div>{msg.text}</div>
            </li>
          ) : (
            <li key={i} className="border border-rule p-3">
              <div className="text-xs font-medium text-muted">agent</div>
              {msg.steps.length > 0 && (
                <ul
                  aria-label="Étapes de l'agent"
                  aria-live="polite"
                  className="mb-2 mt-1 divide-y divide-rule/50 border-y border-rule/50 text-muted"
                >
                  {msg.steps.map((step) => (
                    <li key={step.id} className="py-1 [overflow-wrap:anywhere]">
                      {step.text}
                      {step.ok === false && (
                        <span className="font-medium text-signal-ink"> — échec</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {msg.approval && (
                <div
                  role="group"
                  aria-label={`Ordre proposé : ${
                    msg.approval.side === "buy" ? "acheter" : "vendre"
                  } ${msg.approval.quantity} ${msg.approval.symbol}`}
                  className="mb-2 border border-rule bg-wash p-2"
                >
                  <p className="font-medium">
                    Ordre proposé : {msg.approval.side === "buy" ? "acheter" : "vendre"}{" "}
                    {msg.approval.quantity} {msg.approval.symbol}
                  </p>
                  {msg.approval.decision ? (
                    <p className="mt-1 text-muted">
                      {msg.approval.decision === "approved" ? "Validé" : "Refusé"} —{" "}
                      {msg.approval.decision === "approved"
                        ? "ordre exécuté"
                        : "aucun ordre exécuté"}
                    </p>
                  ) : (
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        onClick={() => decideApproval(msg.approval!.runId, "approved")}
                        className="bg-ink px-3 py-1 font-medium text-paper hover:bg-signal"
                      >
                        Valider
                      </button>
                      <button
                        type="button"
                        onClick={() => decideApproval(msg.approval!.runId, "refused")}
                        className="border border-signal px-3 py-1 font-medium text-signal-ink hover:bg-signal-wash"
                      >
                        Refuser
                      </button>
                    </div>
                  )}
                  {msg.approval.error && (
                    <p role="alert" className="mt-1 text-signal-ink">
                      {msg.approval.error}
                    </p>
                  )}
                </div>
              )}
              {msg.answer && <div className="whitespace-pre-wrap [overflow-wrap:anywhere]">{msg.answer}</div>}
              {msg.summary && <div className="mt-2 text-muted">{msg.summary}</div>}
              {msg.runId && (
                <div className="mt-2">
                  <Link
                    to="/traces"
                    search={{ run: msg.runId }}
                    className="font-medium text-signal-ink underline hover:text-ink"
                  >
                    Voir la trace
                  </Link>
                </div>
              )}
              {msg.stopped && (
                <div className="mt-2 font-medium text-caution-ink">
                  Flux interrompu par l'utilisateur.
                </div>
              )}
            </li>
          ),
        )}
      </ol>
    </section>
  );
}
