import { useEffect, useRef, useState, type FormEvent } from "react";
import { streamAgentRun, type AgentEvent } from "../api";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";
import { isAbortError } from "../lib/errors";

interface Step {
  id: number;
  text: string;
  ok?: boolean;
}

interface ChatMessage {
  role: "user" | "assistant";
  text?: string;
  steps: Step[];
  answer?: string;
  summary?: string;
  stopped?: boolean;
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
          } else if (evt.kind === "answer") {
            patchLastAssistant((msg) => ({ ...msg, answer: evt.payload.text }));
          } else if (evt.kind === "done") {
            patchLastAssistant((msg) => ({
              ...msg,
              summary: `Terminé en ${evt.payload.turns} tours · coût ${evt.payload.cost_cents} c · statut ${evt.payload.status}`,
            }));
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

  return (
    <section aria-labelledby="agent-title">
      <h1 id="agent-title" className="mb-3 text-lg font-bold">
        Conseils de l'agent
      </h1>

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
            className="bg-ink px-4 py-2 font-bold text-paper hover:bg-signal disabled:opacity-50 disabled:hover:bg-ink"
          >
            Envoyer
          </button>
          {running && (
            <button
              type="button"
              onClick={stop}
              className="border border-signal px-4 py-2 font-bold text-signal-ink hover:bg-signal-wash"
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
                        <span className="font-bold text-signal-ink"> — échec</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {msg.answer && <div className="whitespace-pre-wrap [overflow-wrap:anywhere]">{msg.answer}</div>}
              {msg.summary && <div className="mt-2 text-muted">{msg.summary}</div>}
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
