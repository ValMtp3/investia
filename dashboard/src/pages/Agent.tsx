import { useRef, useState, type FormEvent } from "react";
import { streamAgentRun, type AgentEvent } from "../api";

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
      if ((err as Error).name === "AbortError") {
        patchLastAssistant((msg) => ({ ...msg, stopped: true }));
      } else {
        setError(err instanceof Error ? err.message : "Erreur inconnue");
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
      <h1 id="agent-title" className="text-2xl font-bold mb-4">
        Conseils de l'agent
      </h1>

      <form onSubmit={send} className="mb-6 flex gap-2">
        <div className="flex-1">
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
            className="w-full rounded border border-slate-800 bg-slate-900 px-3 py-2 focus-visible:outline-2 focus-visible:outline-sky-400"
          />
        </div>
        <button
          type="submit"
          disabled={running || !input.trim()}
          className="rounded bg-sky-600 px-4 py-2 font-semibold hover:bg-sky-500 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          Envoyer
        </button>
        {running && (
          <button
            type="button"
            onClick={stop}
            className="rounded border border-red-500/60 px-4 py-2 text-red-300 hover:bg-red-500/10 focus-visible:outline-2 focus-visible:outline-red-400"
          >
            Stop
          </button>
        )}
      </form>

      {running && (
        <p role="status" className="mb-4 text-sm text-slate-400">
          L'agent réfléchit…
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 rounded border border-red-500/50 bg-red-500/10 p-3 text-red-300">
          {error}
        </p>
      )}

      <ol className="space-y-4">
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <li key={i} className="rounded border border-slate-800 bg-slate-900 p-3">
              <div className="text-xs text-slate-500">toi</div>
              <div>{msg.text}</div>
            </li>
          ) : (
            <li key={i} className="rounded border border-slate-800 p-3">
              <div className="text-xs text-slate-500">agent</div>
              {msg.steps.length > 0 && (
                <ul
                  aria-label="Étapes de l'agent"
                  aria-live="polite"
                  className="mb-2 space-y-1 text-sm text-slate-400"
                >
                  {msg.steps.map((step) => (
                    <li key={step.id}>
                      {step.text}
                      {step.ok === false && (
                        <span className="text-red-400"> — échec</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {msg.answer && <div className="whitespace-pre-wrap">{msg.answer}</div>}
              {msg.summary && <div className="mt-2 text-sm text-slate-400">{msg.summary}</div>}
              {msg.stopped && (
                <div className="mt-2 text-sm text-amber-300">Flux interrompu par l'utilisateur.</div>
              )}
            </li>
          ),
        )}
      </ol>
    </section>
  );
}
