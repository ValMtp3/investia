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
// Le backend garde l'historique 1 h en cache : inutile de le redemander à chaque clic.
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
  return response.json() as Promise<MarketHistory>;
}

export function useMarketHistory(symbol: string) {
  return useQuery({
    queryKey: ["market-history", symbol],
    queryFn: ({ signal }) => fetchMarketHistory(symbol, signal),
    staleTime: HISTORY_STALE_MS,
  });
}

// --- Flux SSE (étape 4.4) ---

export type AgentEvent =
  | { kind: "start"; payload: { question: string; max_turns: number } }
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
