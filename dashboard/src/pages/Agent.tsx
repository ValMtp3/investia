import { useEffect, useRef, useState, type ComponentType, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { A2UIStore, type A2UISurfaceModel } from "../a2ui";
import {
  fetchTrace,
  isPortfolioPayload,
  respondApproval,
  streamAgentRun,
  streamMultiAgentRun,
  usePortfolio,
  type AgentEvent,
  type RunState,
  type StreamResume,
} from "../api";
import A2UISurface from "../components/A2UISurface";
import Badge from "../components/Badge";
import ErrorNotice from "../components/ErrorNotice";
import HistoryChart from "../components/HistoryChart";
import Markdown from "../components/Markdown";
import Module from "../components/Module";
import Skeleton from "../components/Skeleton";
import PageHeader from "../components/PageHeader";
import Stat from "../components/Stat";
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
  /** 24 : bearer token reçu dans l'event approval_request, renvoyé au POST. */
  token?: string;
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
  /** 21a : état partagé du run (StateSnapshotEvent AG-UI), mis à jour en direct. */
  runState?: RunState;
  /** 21b : composants poussés par l'agent (generative UI), rendus via la whitelist. */
  components?: { component: string; props: Record<string, unknown> }[];
}

/** 21b : whitelist des composants rendus depuis le flux AG-UI — rien d'autre ne peut
 *  être instancié (un composant inconnu est ignoré, jamais de HTML arbitraire).
 *  `any` sur les props : la whitelist est la barrière, le composant valide lui-même. */
const UI_COMPONENTS: Record<string, ComponentType<any>> = {
  HistoryChart,
};

// 23f : reconnexion SSE (Last-Event-ID) — backoff puis abandon après 3 essais.
const RETRY_DELAYS_MS = [500, 1000, 2000];
// 23f : après un event `detached` (run encore actif côté serveur), on poll la trace.
const POLL_INTERVAL_MS = 2000;
const POLL_MAX = 150; // ~5 min max

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Questions prêtes à l'emploi : un clic remplit le champ (l'envoi reste manuel). */
const SUGGESTIONS = [
  "Quel est le prix de AAPL ?",
  "Analyse mon portefeuille simulé",
  "Donne-moi l'historique de BTC-USD sur 90 jours",
];

/** Modes d'exécution avec leur explication, affichée sous le sélecteur quel que soit le mode. */
const MODES = [
  {
    value: "solo" as const,
    label: "Agent seul",
    hint: "Un seul agent répond, avec les outils marché et portefeuille.",
  },
  {
    value: "multi" as const,
    label: "Multi-agents (A2A)",
    hint: "Chaîne A2A : analyste → gestionnaire de risque → rédacteur.",
  },
];

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
    case "a2a_delegate": {
      const status =
        event.payload.status === "ok"
          ? "ok"
          : event.payload.status === "error"
            ? "erreur"
            : "en cours…";
      return {
        text: `Délégation A2A → ${event.payload.agent} (${status})`,
        ok: event.payload.status === "ok" ? true : event.payload.status === "error" ? false : undefined,
      };
    }
    case "a2a_event": {
      // 20c : step interne d'un sous-agent (streaming A2A) — on réutilise le
      // rendu du mode solo, préfixé du nom de l'agent délégué.
      const inner = stepText({
        kind: event.payload.event_kind,
        payload: event.payload.payload,
      } as AgentEvent);
      const detail = inner ? inner.text : event.payload.event_kind;
      return {
        text: `→ ${event.payload.agent} · ${detail}`,
        ok: inner?.ok,
      };
    }
    default:
      return null;
  }
}

export default function Agent() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Mode d'exécution : agent seul (défaut) ou chaîne multi-agents A2A (6.1).
  const [mode, setMode] = useState<"solo" | "multi">("solo");
  const abortRef = useRef<AbortController | null>(null);
  const stepIdRef = useRef(0);
  const statusRef = useRef<HTMLParagraphElement | null>(null);
  // 23f : reconnexion — dernier id SSE reçu, run_id courant, flag detached
  const lastEventIdRef = useRef<number | null>(null);
  const runIdRef = useRef<string | null>(null);
  const detachedRef = useRef(false);
  // Résumé du portefeuille simulé (l'agent y a accès via l'outil get_portfolio).
  const portfolio = usePortfolio();
  // 23c : ?protocol=a2ui branche le flux A2UI 1.0 (défaut : agui, 21a).
  const protocol: "agui" | "a2ui" =
    new URLSearchParams(window.location.search).get("protocol") === "a2ui" ? "a2ui" : "agui";
  const a2uiStoreRef = useRef(new A2UIStore());
  const [a2uiSurfaces, setA2uiSurfaces] = useState<A2UISurfaceModel[]>([]);

  // Quitter la page coupe le flux : sinon le run continue (et coûte des appels au modèle).
  useEffect(() => () => abortRef.current?.abort(), []);

  // À l'envoi, le focus part sur le statut « réfléchit » : au clavier, on suit le run
  // au lieu de rester sur un bouton Envoyer devenu disabled.
  useEffect(() => {
    if (running) statusRef.current?.focus();
  }, [running]);

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
    a2uiStoreRef.current = new A2UIStore();
    setA2uiSurfaces([]);
    lastEventIdRef.current = null;
    runIdRef.current = null;
    detachedRef.current = false;

    /** Met à jour la dernière bulle assistant selon l'event (21a/23c/23f). */
    const handleEvent = (evt: AgentEvent) => {
          if (evt.kind === "state_snapshot") {
            // 21a : état partagé AG-UI — panneau « État du run » mis à jour en direct
            patchLastAssistant((msg) => ({ ...msg, runState: evt.payload }));
            return;
          }
          if (evt.kind === "a2ui") {
            // 23c : message A2UI 1.0 — surfaces rendues via le catalogue whitelisté
            a2uiStoreRef.current.apply(evt.payload);
            setA2uiSurfaces(a2uiStoreRef.current.list());
            return;
          }
          if (evt.kind === "ui_component") {
            // 21b : generative UI — whitelist : composant inconnu ignoré
            if (!(evt.payload.component in UI_COMPONENTS)) return;
            patchLastAssistant((msg) => ({
              ...msg,
              components: [
                ...(msg.components ?? []),
                { component: evt.payload.component, props: evt.payload.props },
              ],
            }));
            return;
          }
          const step = stepText(evt);
          if (step) {
            stepIdRef.current += 1;
            const id = stepIdRef.current;
            patchLastAssistant((msg) => ({
              ...msg,
              steps: [...msg.steps, { id, text: step.text, ok: step.ok }],
            }));
          } else if (evt.kind === "start") {
            // Le run est tracé côté backend : on garde son id pour le lien « voir la trace »
            // et pour la reconnexion 23f (re-POST avec run_id + Last-Event-ID).
            if (evt.payload.run_id) runIdRef.current = evt.payload.run_id;
            patchLastAssistant((msg) => ({ ...msg, runId: evt.payload.run_id ?? null }));
          } else if (evt.kind === "detached") {
            // 23f : run encore actif côté serveur -> on replie en polling de la trace
            detachedRef.current = true;
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
                token: evt.payload.approval_token,
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
    };

    /** 23f : poll GET /traces/{run_id} jusqu'au statut final (repli après detached). */
    const pollRunUntilFinished = async (runId: string) => {
      for (let i = 0; i < POLL_MAX; i++) {
        const trace = await fetchTrace(runId, controller.signal);
        const run = trace.run;
        if (!run || run.status !== "running") {
          if (run) {
            if (run.answer) {
              patchLastAssistant((msg) => ({ ...msg, answer: run.answer ?? msg.answer }));
            }
            patchLastAssistant((msg) => ({
              ...msg,
              summary: `Terminé en ${run.turns} tours · coût ${run.total_cost_cents} c · statut ${run.status}`,
            }));
          }
          return;
        }
        await sleep(POLL_INTERVAL_MS);
      }
    };

    try {
      let resume: StreamResume | null = null;
      let attempt = 0;
      for (;;) {
        try {
          if (mode === "multi") {
            // 23f hors périmètre : le multi-agents n'a pas de replay (v2)
            await streamMultiAgentRun(
              question,
              (evt, eventId) => {
                if (eventId != null) lastEventIdRef.current = eventId;
                handleEvent(evt);
              },
              controller.signal,
              protocol, // 21a : AG-UI par défaut ; 23c : A2UI 1.0 avec ?protocol=a2ui
            );
          } else {
            await streamAgentRun(
              question,
              (evt, eventId) => {
                if (eventId != null) lastEventIdRef.current = eventId;
                handleEvent(evt);
              },
              controller.signal,
              protocol,
              resume ?? undefined, // 23f : replay du run avec le dernier id reçu
            );
          }
          break;
        } catch (err) {
          if (isAbortError(err)) throw err; // stop volontaire -> gestionnaire externe
          if (detachedRef.current) break; // run actif ailleurs -> polling ci-dessous
          if (runIdRef.current) {
            resume = { runId: runIdRef.current, lastEventId: lastEventIdRef.current };
          }
          attempt += 1;
          if (!resume || attempt > RETRY_DELAYS_MS.length) throw err;
          await sleep(RETRY_DELAYS_MS[attempt - 1]);
        }
      }
      if (detachedRef.current && runIdRef.current) {
        await pollRunUntilFinished(runIdRef.current);
      }
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
  async function decideApproval(
    runId: string,
    decision: "approved" | "refused",
    token?: string,
  ) {
    const patch = (msg: ChatMessage): ChatMessage =>
      msg.approval && msg.approval.runId === runId
        ? { ...msg, approval: { ...msg.approval, decision, error: undefined } }
        : msg;
    try {
      await respondApproval(runId, decision, token);
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
      <PageHeader
        id="agent-title"
        title="Conseils de l'agent"
        subtitle="Réponses en streaming (SSE) — chaque étape du raisonnement est tracée, chaque ordre simulé demande ta validation."
      />

      <Module title="Portefeuille simulé" className="mb-3">
        {portfolio.isLoading && (
          <Skeleton label="Chargement du portefeuille…" />
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
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              <Stat
                label="Valeur totale"
                value={formatMoney(portfolio.data.total_value, portfolio.data.currency)}
              />
              <Stat
                label="Cash"
                value={formatMoney(portfolio.data.cash, portfolio.data.currency)}
              />
              <Stat
                label="Positions"
                value={formatMoney(portfolio.data.positions_value, portfolio.data.currency)}
              />
            </div>
            {portfolio.data.positions.length > 0 && (
              <p className="mt-2 text-muted">
                {portfolio.data.positions.map((position) => position.symbol).join(", ")}
              </p>
            )}
          </>
        )}
      </Module>

      <Module title="Demande à l'agent" className="mb-3">
        <div
          role="group"
          aria-label="Mode d'exécution"
          className="mb-1 flex overflow-hidden border border-rule-strong"
        >
          {MODES.map((option, index) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={mode === option.value}
              onClick={() => setMode(option.value)}
              className={`min-h-11 flex-1 px-3 py-1 font-medium ${
                index === 0 ? "border-r border-rule-strong" : ""
              } ${
                mode === option.value
                  ? "bg-wash text-signal-ink"
                  : "bg-paper text-muted hover:bg-wash"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="mb-2 text-xs text-muted">
          {MODES.find((option) => option.value === mode)?.hint}
        </p>
        <div role="group" aria-label="Suggestions" className="mb-2 flex flex-wrap gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => setInput(suggestion)}
              className="min-h-11 border border-rule-strong bg-paper px-3 py-1 text-sm hover:bg-wash"
            >
              {suggestion}
            </button>
          ))}
        </div>
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
              className="min-h-11 w-full border border-rule-strong bg-bg px-3 py-2 placeholder:text-muted"
            />
          </div>
          <button
            type="submit"
            disabled={running || !input.trim()}
            className="min-h-11 bg-signal px-4 py-2 font-medium text-on-signal hover:bg-[#b91e17] disabled:opacity-50"
          >
            Envoyer
          </button>
          {running && (
            <button
              type="button"
              onClick={stop}
              className="min-h-11 border border-signal px-4 py-2 font-medium text-signal-ink hover:bg-signal-wash"
            >
              Stop
            </button>
          )}
        </form>
      </Module>

      {running && (
        <p
          ref={statusRef}
          role="status"
          tabIndex={-1}
          className="mb-3 text-muted focus:outline-none"
        >
          L'agent réfléchit…
        </p>
      )}
      {error && <ErrorNotice className="mb-3">{error}</ErrorNotice>}

      <ol aria-label="Conversation" className="space-y-3">
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <li key={i} className="border border-rule bg-wash p-3">
              <Badge tone="neutral" className="mb-1">
                toi
              </Badge>
              <div className="[overflow-wrap:anywhere]">{msg.text}</div>
            </li>
          ) : (
            <li key={i} className="border border-rule bg-paper p-3">
              <Badge tone="signal" className="mb-1">
                agent
              </Badge>
              {msg.steps.length > 0 && (
                <ul
                  aria-label="Étapes de l'agent"
                  aria-live="polite"
                  className="mb-2 mt-1 divide-y divide-rule border-y border-rule text-muted"
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
              {msg.components?.map((c, i) => {
                const Comp = UI_COMPONENTS[c.component];
                if (!Comp) return null;
                return (
                  <div
                    key={i}
                    aria-label={`Composant ${c.component}`}
                    className="mb-2 mt-1 border border-rule bg-wash/50 p-2"
                  >
                    <Comp {...c.props} />
                  </div>
                );
              })}
              {msg.runState && (
                <div
                  aria-label="État du run"
                  className="mb-2 mt-1 border border-rule bg-wash/50 p-2 text-xs text-muted"
                >
                  <p className="mb-1 flex flex-wrap items-center gap-2">
                    <span>État du run</span>
                    <Badge tone={msg.runState.status === "ok" ? "gain" : "neutral"}>
                      {msg.runState.status}
                    </Badge>
                    {msg.runState.agents.map((a) => (
                      <Badge key={a}>{a}</Badge>
                    ))}
                  </p>
                  <ol aria-label="Étapes structurées du run" className="space-y-0.5">
                    {msg.runState.steps.slice(-8).map((s, i) => (
                      <li key={i} className="[overflow-wrap:anywhere]">
                        {s.summary}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {msg.approval && (
                <div
                  role="group"
                  aria-label={`Ordre proposé : ${
                    msg.approval.side === "buy" ? "acheter" : "vendre"
                  } ${msg.approval.quantity} ${msg.approval.symbol}`}
                  className="mb-2 border border-signal bg-signal-wash p-3"
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
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          decideApproval(msg.approval!.runId, "approved", msg.approval!.token)
                        }
                        className="min-h-11 bg-signal px-3 py-1 font-medium text-on-signal hover:brightness-110"
                      >
                        Valider
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          decideApproval(msg.approval!.runId, "refused", msg.approval!.token)
                        }
                        className="min-h-11 border border-rule-strong px-3 py-1 font-medium text-ink hover:bg-wash"
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
              {msg.answer && (
                <div className="[overflow-wrap:anywhere]">
                  {/* 23f : markdown streamé (streamdown) — la DA du conteneur est inchangée */}
                  <Markdown>{msg.answer}</Markdown>
                </div>
              )}
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

      {a2uiSurfaces.length > 0 && (
        <div aria-label="Surfaces A2UI" className="mt-3">
          {a2uiSurfaces.map((surface) => (
            <A2UISurface key={surface.surfaceId} surface={surface} />
          ))}
        </div>
      )}
    </section>
  );
}
