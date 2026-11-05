import { useMemo, useState } from "react";
import { useSearch } from "@tanstack/react-router";
import type { UTCTimestamp } from "lightweight-charts";
import { useEvals, useTrace, useTraces, type EvalRun } from "../api";
import ErrorNotice from "../components/ErrorNotice";
import EvalChart, { type EvalSeries } from "../components/EvalChart";
import Module from "../components/Module";
import { formatDateTime } from "../lib/format";

const SERIES_COLORS = ["#d7261e", "#1a56db", "#0b7a43", "#6b4a00", "#1b1f23", "#55606a"];

function statusLabel(status: string): string {
  switch (status) {
    case "ok":
      return "ok";
    case "blocked":
      return "bloqué";
    case "max_turns":
      return "tours max atteints";
    case "error":
      return "erreur";
    case "running":
      return "en cours";
    default:
      return status;
  }
}

function toUnixSeconds(iso: string): UTCTimestamp {
  const ms = new Date(iso).getTime();
  return (Number.isNaN(ms) ? 0 : Math.floor(ms / 1000)) as UTCTimestamp;
}

/** Score moyen par métrique et par run d'eval, trié du plus ancien au plus récent. */
function aggregateEvals(runs: EvalRun[]): EvalSeries[] {
  const byMetric = new Map<string, { at: UTCTimestamp; sum: number; count: number }[]>();
  const sorted = [...runs].sort((a, b) => a.started_at.localeCompare(b.started_at));
  for (const run of sorted) {
    const sums = new Map<string, { sum: number; count: number }>();
    for (const result of run.results) {
      const acc = sums.get(result.metric) ?? { sum: 0, count: 0 };
      acc.sum += result.score;
      acc.count += 1;
      sums.set(result.metric, acc);
    }
    for (const [metric, acc] of sums) {
      const list = byMetric.get(metric) ?? [];
      list.push({ at: toUnixSeconds(run.started_at), sum: acc.sum, count: acc.count });
      byMetric.set(metric, list);
    }
  }
  return [...byMetric.entries()].map(([name, points], i) => ({
    name,
    color: SERIES_COLORS[i % SERIES_COLORS.length],
    points: points.map((p) => ({ time: p.at, value: p.count > 0 ? p.sum / p.count : 0 })),
  }));
}

export default function Traces() {
  // ?run=<id> présélectionne l'exécution (lien « voir la trace » de la page Agent).
  const { run: preselectedRun } = useSearch({ from: "/traces" });
  const [selectedId, setSelectedId] = useState<string | null>(preselectedRun ?? null);
  const traces = useTraces(50);
  const detail = useTrace(selectedId);
  const evals = useEvals();
  const evalSeries = useMemo(
    () => (evals.data ? aggregateEvals(evals.data.runs) : []),
    [evals.data],
  );

  return (
    <section aria-labelledby="traces-title">
      <h1 id="traces-title" className="mb-3 text-lg font-medium">
        Traces & évaluations
      </h1>
      <div className="grid gap-3 lg:grid-cols-[22rem_1fr]">
        <Module title="Exécutions" className="min-w-0">
          {traces.isLoading && (
            <p role="status" className="text-muted">
              Chargement des exécutions…
            </p>
          )}
          {traces.isError && (
            <ErrorNotice>
              Erreur :{" "}
              {traces.error instanceof Error ? traces.error.message : "API indisponible"}
            </ErrorNotice>
          )}
          {traces.data &&
            (traces.data.runs.length === 0 ? (
              <p className="text-muted">Aucune exécution pour l'instant.</p>
            ) : (
              <ul aria-label="Exécutions de l'agent" className="-mx-2 divide-y divide-rule">
                {traces.data.runs.map((run) => (
                  <li key={run.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(run.id)}
                      aria-pressed={selectedId === run.id}
                      className="block w-full px-2 py-2 text-left hover:bg-wash aria-pressed:bg-wash"
                    >
                      <div className="text-xs text-muted">
                        {formatDateTime(run.created_at)} · {statusLabel(run.status)}
                      </div>
                      <div className="font-medium [overflow-wrap:anywhere]">{run.question}</div>
                      <div className="text-xs text-muted">
                        {run.turns} tours · {run.total_cost_cents.toLocaleString("fr-FR")} c
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ))}
        </Module>

        <Module title="Détail de l'exécution" className="min-w-0">
          {!selectedId && (
            <p className="text-muted">Sélectionne une exécution pour voir ses étapes.</p>
          )}
          {selectedId && detail.isLoading && (
            <p role="status" className="text-muted">
              Chargement de la trace…
            </p>
          )}
          {selectedId && detail.isError && (
            <ErrorNotice>
              Erreur :{" "}
              {detail.error instanceof Error ? detail.error.message : "API indisponible"}
            </ErrorNotice>
          )}
          {selectedId && detail.data?.run && (
            <div>
              <div className="mb-2 text-xs text-muted">
                {formatDateTime(detail.data.run.created_at)} · {statusLabel(detail.data.run.status)}{" "}
                · {detail.data.run.model ?? "modèle inconnu"} · {detail.data.run.turns} tours ·{" "}
                {detail.data.run.total_cost_cents.toLocaleString("fr-FR")} c
              </div>
              <p className="mb-3 font-medium [overflow-wrap:anywhere]">
                {detail.data.run.question}
              </p>
              {detail.data.run.answer && (
                <div className="mb-3 whitespace-pre-wrap border border-rule bg-wash p-3 [overflow-wrap:anywhere]">
                  {detail.data.run.answer}
                </div>
              )}
              <h3 className="mb-1 text-sm font-medium">Étapes</h3>
              {detail.data.steps.length === 0 ? (
                <p className="text-muted">Aucune étape enregistrée.</p>
              ) : (
                <ol
                  aria-label="Étapes de l'exécution"
                  className="divide-y divide-rule/50 border-y border-rule/50"
                >
                  {detail.data.steps.map((step, i) => (
                    <li key={i} className="py-1 text-sm">
                      <span className="text-muted">
                        {formatDateTime(step.created_at)} · tour {step.turn}
                      </span>{" "}
                      <span className="font-medium">{step.kind}</span>{" "}
                      <span className="text-muted [overflow-wrap:anywhere]">
                        {JSON.stringify(step.payload)}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </Module>
      </div>

      <Module title="Évaluations" className="mt-3 min-w-0">
        {evals.isLoading && (
          <p role="status" className="text-muted">
            Chargement des évaluations…
          </p>
        )}
        {evals.isError && (
          <ErrorNotice>
            Erreur : {evals.error instanceof Error ? evals.error.message : "API indisponible"}
          </ErrorNotice>
        )}
        {evals.data &&
          (evalSeries.length === 0 ? (
            <p className="text-muted">Aucune évaluation enregistrée pour l'instant.</p>
          ) : (
            <>
              <ul aria-label="Métriques" className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
                {evalSeries.map((oneSeries) => (
                  <li key={oneSeries.name} className="flex items-center gap-2 text-sm">
                    <span
                      aria-hidden="true"
                      className="inline-block h-0.5 w-4"
                      style={{ backgroundColor: oneSeries.color }}
                    />
                    {oneSeries.name}
                  </li>
                ))}
              </ul>
              <EvalChart
                series={evalSeries}
                label="Scores des évaluations dans le temps, une courbe par métrique (moyenne par run d'eval)"
              />
              <p className="mt-1 text-xs text-muted">
                Score moyen par métrique et par run d'eval, du plus ancien au plus récent.
              </p>
            </>
          ))}
      </Module>
    </section>
  );
}
