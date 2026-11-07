// Client API : tout passe par le backend (les clés API restent côté serveur).
import { useQuery } from "@tanstack/react-query";
import { streamSse } from "./lib/sse";

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  price_eur: number;
  value_eur: number;
  source: string;
  price_timestamp: string;
}

export interface Portfolio {
  cash: number;
  positions: Position[];
  positions_value: number;
  total_value: number;
  currency: string;
}

export async function fetchPortfolio(): Promise<Portfolio> {
  const response = await fetch(`${API_URL}/portfolio`);
  if (!response.ok) {
    throw new Error(`API indisponible (HTTP ${response.status})`);
  }
  return response.json() as Promise<Portfolio>;
}

export function usePortfolio() {
  return useQuery({ queryKey: ["portfolio"], queryFn: fetchPortfolio });
}

// --- Historique des cours (étape 4.4c) ---

/** Période demandée au backend, et affichée dans le texte alternatif du graphique. */
export const HISTORY_DAYS = 30;
// Le backend garde l'historique 24 h en cache : inutile de le redemander à chaque clic.
const HISTORY_STALE_MS = 5 * 60 * 1000;

export interface HistoryPoint {
  time: string; // jour au format AAAA-MM-JJ
  value: number; // cours de clôture
}

export interface MarketHistory {
  symbol: string;
  source: string | null;
  currency: string | null;
  delayed: boolean;
  points: HistoryPoint[];
}

/** Message d'erreur du backend (`{"detail": "..."}`), ou `fallback` s'il n'est pas lisible. */
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
  } catch {
    // Corps absent ou pas du JSON : on garde le message générique.
  }
  return fallback;
}

function isHistoryPoint(point: unknown): point is HistoryPoint {
  if (typeof point !== "object" || point === null) return false;
  const { time, value } = point as Partial<HistoryPoint>;
  return typeof time === "string" && typeof value === "number" && Number.isFinite(value);
}

/** Les dates AAAA-MM-JJ se comparent comme du texte : strictement croissantes, sans doublon. */
function isStrictlyAscending(points: HistoryPoint[]): boolean {
  return points.every((point, i) => i === 0 || points[i - 1].time < point.time);
}

/** Vérifie la forme de la réponse : le graphique plante sur des points mal formés. */
function parseMarketHistory(raw: unknown): MarketHistory {
  const points = (raw as Partial<MarketHistory> | null)?.points;
  if (!Array.isArray(points) || !points.every(isHistoryPoint) || !isStrictlyAscending(points)) {
    throw new Error("Historique reçu illisible : réponse inattendue du serveur.");
  }
  return raw as MarketHistory;
}

export async function fetchMarketHistory(
  symbol: string,
  signal?: AbortSignal,
): Promise<MarketHistory> {
  const params = new URLSearchParams({ symbol, days: String(HISTORY_DAYS) });
  const response = await fetch(`${API_URL}/market/history?${params.toString()}`, { signal });
  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Historique indisponible (HTTP ${response.status})`),
    );
  }
  return parseMarketHistory(await response.json());
}

export function useMarketHistory(symbol: string) {
  return useQuery({
    queryKey: ["market-history", symbol],
    queryFn: ({ signal }) => fetchMarketHistory(symbol, signal),
    staleTime: HISTORY_STALE_MS,
    // Le backend explique déjà l'échec (« eodhd: clé API manquante ») : on l'affiche tout
    // de suite plutôt que de réessayer 3 fois (environ 7 s sur « Chargement… »).
    retry: false,
  });
}

// --- Flux SSE (étape 4.4) ---

export type AgentEvent =
  | {
      kind: "start";
      payload: { question: string; max_turns: number; run_id?: string | null };
    }
  | {
      kind: "llm_call";
      payload: {
        turn: number;
        model: string;
        cost_cents: number;
        tool_calls: string[];
      };
    }
  | {
      kind: "tool_call";
      payload: {
        turn: number;
        name: string;
        arguments: Record<string, unknown>;
        ok: boolean;
      };
    }
  | {
      kind: "guardrail";
      payload: { turn: number; check: string; ok: boolean; detail: string };
    }
  | { kind: "answer"; payload: { turn: number; text: string } }
  | { kind: "error"; payload: { message: string } }
  | {
      kind: "approval_request";
      payload: {
        run_id: string;
        turn: number;
        symbol: string;
        side: "buy" | "sell";
        quantity: number;
      };
    }
  | {
      kind: "approval";
      payload: {
        turn: number;
        decision: string;
        symbol: string;
        side: "buy" | "sell";
        quantity: number;
      };
    }
  | { kind: "done"; payload: { turns: number; cost_cents: number; status: string } };

/** Stream SSE de la boucle agent : POST /agent/run. */
export function streamAgentRun(
  question: string,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse(`${API_URL}/agent/run`, {
    method: "POST",
    body: { question },
    signal,
    onEvent: (kind, data) => onEvent({ kind, payload: data } as AgentEvent),
  });
}

/** Décision humaine sur un ordre proposé (étape 5.1) : POST /agent/runs/:id/approval. */
export async function respondApproval(
  runId: string,
  decision: "approved" | "refused",
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_URL}/agent/runs/${encodeURIComponent(runId)}/approval`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Approbation indisponible (HTTP ${response.status})`),
    );
  }
}

export interface LiveQuote {
  symbol: string;
  value?: number;
  currency?: string;
  source?: string;
  timestamp?: string;
  delayed?: boolean;
  // Vrai si le prix en direct a échoué : on affiche la dernière clôture à la place.
  is_close?: boolean;
  error?: string;
}

/** Stream SSE des prix : GET /market/stream?symbols=AAPL,SAP.DE. */
export function streamMarket(
  symbols: string[],
  onQuotes: (quotes: LiveQuote[]) => void,
  signal?: AbortSignal,
): Promise<void> {
  const params = new URLSearchParams({ symbols: symbols.join(",") });
  return streamSse(`${API_URL}/market/stream?${params.toString()}`, {
    signal,
    onEvent: (kind, data) => {
      if (kind === "quotes") {
        onQuotes((data as { quotes: LiveQuote[] }).quotes);
      }
    },
  });
}

// --- Traces & evals (étape 4.5) ---

export interface TraceRunSummary {
  id: string;
  question: string;
  status: string;
  model: string | null;
  turns: number;
  total_cost_cents: number;
  created_at: string;
}

export interface TraceStep {
  turn: number;
  kind: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TraceRunDetail extends TraceRunSummary {
  answer: string | null;
}

export interface TraceDetail {
  run: TraceRunDetail | null;
  steps: TraceStep[];
}

export interface EvalResult {
  case_id: string;
  metric: string;
  score: number;
}

export interface EvalRun {
  id: string;
  started_at: string;
  model: string | null;
  commit: string | null;
  mode: string;
  results: EvalResult[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTraceRunSummary(raw: unknown): raw is TraceRunSummary {
  return (
    isRecord(raw) &&
    typeof raw.id === "string" &&
    typeof raw.question === "string" &&
    typeof raw.status === "string" &&
    (raw.model === null || typeof raw.model === "string") &&
    typeof raw.turns === "number" &&
    typeof raw.total_cost_cents === "number" &&
    typeof raw.created_at === "string"
  );
}

function isTraceRunDetail(raw: unknown): raw is TraceRunDetail {
  return (
    isRecord(raw) &&
    (raw.answer === null || typeof raw.answer === "string") &&
    isTraceRunSummary(raw)
  );
}

function isTraceStep(raw: unknown): raw is TraceStep {
  return (
    isRecord(raw) &&
    typeof raw.turn === "number" &&
    typeof raw.kind === "string" &&
    isRecord(raw.payload) &&
    typeof raw.created_at === "string"
  );
}

function isEvalResult(raw: unknown): raw is EvalResult {
  return (
    isRecord(raw) &&
    typeof raw.case_id === "string" &&
    typeof raw.metric === "string" &&
    typeof raw.score === "number"
  );
}

function isEvalRun(raw: unknown): raw is EvalRun {
  return (
    isRecord(raw) &&
    typeof raw.id === "string" &&
    typeof raw.started_at === "string" &&
    (raw.model === null || typeof raw.model === "string") &&
    (raw.commit === null || typeof raw.commit === "string") &&
    typeof raw.mode === "string" &&
    Array.isArray(raw.results) &&
    raw.results.every(isEvalResult)
  );
}

/** Vérifie la forme de la réponse : on n'affiche jamais une donnée illisible. */
function parseTraces(raw: unknown): { runs: TraceRunSummary[] } {
  const runs = (raw as { runs?: unknown } | null)?.runs;
  if (!Array.isArray(runs) || !runs.every(isTraceRunSummary)) {
    throw new Error("Traces reçues illisibles : réponse inattendue du serveur.");
  }
  return { runs };
}

function parseTraceDetail(raw: unknown): TraceDetail {
  if (!isRecord(raw) || !Array.isArray(raw.steps) || !raw.steps.every(isTraceStep)) {
    throw new Error("Détail de la trace illisible : réponse inattendue du serveur.");
  }
  const run = raw.run;
  if (run !== null && !isTraceRunDetail(run)) {
    throw new Error("Détail de la trace illisible : réponse inattendue du serveur.");
  }
  return { run, steps: raw.steps };
}

function parseEvals(raw: unknown): { runs: EvalRun[] } {
  const runs = (raw as { runs?: unknown } | null)?.runs;
  if (!Array.isArray(runs) || !runs.every(isEvalRun)) {
    throw new Error("Evals reçues illisibles : réponse inattendue du serveur.");
  }
  return { runs };
}

export async function fetchTraces(
  limit = 50,
  signal?: AbortSignal,
): Promise<{ runs: TraceRunSummary[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`${API_URL}/traces?${params.toString()}`, { signal });
  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Traces indisponibles (HTTP ${response.status})`),
    );
  }
  return parseTraces(await response.json());
}

export async function fetchTrace(runId: string, signal?: AbortSignal): Promise<TraceDetail> {
  const response = await fetch(`${API_URL}/traces/${encodeURIComponent(runId)}`, { signal });
  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Trace indisponible (HTTP ${response.status})`),
    );
  }
  return parseTraceDetail(await response.json());
}

export async function fetchEvals(signal?: AbortSignal): Promise<{ runs: EvalRun[] }> {
  const response = await fetch(`${API_URL}/evals`, { signal });
  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Evals indisponibles (HTTP ${response.status})`),
    );
  }
  return parseEvals(await response.json());
}

export function useTraces(limit = 50) {
  return useQuery({
    queryKey: ["traces", limit],
    queryFn: ({ signal }) => fetchTraces(limit, signal),
    retry: false,
  });
}

export function useTrace(runId: string | null) {
  return useQuery({
    queryKey: ["trace", runId],
    queryFn: ({ signal }) => fetchTrace(runId as string, signal),
    enabled: runId !== null,
    retry: false,
  });
}

export function useEvals() {
  return useQuery({
    queryKey: ["evals"],
    queryFn: ({ signal }) => fetchEvals(signal),
    retry: false,
  });
}
