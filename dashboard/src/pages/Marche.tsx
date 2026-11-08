import { useEffect, useState } from "react";
import ErrorNotice from "../components/ErrorNotice";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import Loading from "../components/Loading";
import Module from "../components/Module";
import PageHeader from "../components/PageHeader";
import PriceChart from "../components/PriceChart";
import Sparkline from "../components/Sparkline";
import {
  streamMarket,
  useMarketHistory,
  useMarketSearch,
  type HistoryPoint,
  type LiveQuote,
} from "../api";
import { isAbortError } from "../lib/errors";
import { formatPercent } from "../lib/format";

/** Watchlist 100 % perso, persistée en localStorage (étape 7 fix). Max 20 symboles côté backend. */
const WATCHLIST_KEY = "investia.watchlist.v1";
const MAX_SYMBOLS = 20;

function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((s): s is string => typeof s === "string").slice(0, MAX_SYMBOLS);
  } catch {
    return [];
  }
}

function saveWatchlist(symbols: string[]): void {
  try {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(symbols));
  } catch {
    // localStorage indisponible (navigation privée…) : la watchlist reste en mémoire.
  }
}

/** Périodes du graphique : `days` est borné à 5–400 côté backend. */
const PERIODS = [
  { label: "5 j", days: 5 },
  { label: "1 m", days: 30 },
  { label: "3 m", days: 90 },
  { label: "6 m", days: 180 },
  { label: "max", days: 400 },
] as const;

// 1 mois par défaut, comme avant l'étape 7.
type Period = (typeof PERIODS)[number];
const DEFAULT_PERIOD: Period = PERIODS[1];

/** Heure du prix, ou « clôture du 30/10 » : une clôture n'a pas d'heure à afficher. */
function formatAsOf(quote: LiveQuote): string {
  if (!quote.timestamp) return "";
  const date = new Date(quote.timestamp);
  if (Number.isNaN(date.getTime())) return quote.timestamp;
  if (quote.is_close) {
    // UTC : la date de la clôture ne doit pas glisser d'un jour selon le fuseau du lecteur.
    const day = date.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      timeZone: "UTC",
    });
    return `clôture du ${day}`;
  }
  return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** Variations en % calculées depuis les clôtures : jour (avant-dernier → dernier)
 *  et période (premier → dernier). null si pas assez de points. */
function pctChanges(points: HistoryPoint[]): { day: number | null; period: number | null } {
  if (points.length < 2) return { day: null, period: null };
  const first = points[0].value;
  const prev = points[points.length - 2].value;
  const last = points[points.length - 1].value;
  return {
    day: prev !== 0 ? ((last - prev) / prev) * 100 : null,
    period: first !== 0 ? ((last - first) / first) * 100 : null,
  };
}

interface SymbolCardProps {
  symbol: string;
  quote: LiveQuote | undefined;
  selected: boolean;
  days: number;
  periodLabel: string;
  onSelect: () => void;
  onRemove: () => void;
}

/** Carte d'un symbole : prix live, variation du jour, sparkline, bouton retirer. */
function SymbolCard({
  symbol,
  quote,
  selected,
  days,
  periodLabel,
  onSelect,
  onRemove,
}: SymbolCardProps) {
  const history = useMarketHistory(symbol, days);
  const points = history.data?.points ?? [];
  const changes = pctChanges(points);
  const sparkTone =
    changes.period === null ? "neutral" : changes.period >= 0 ? "gain" : "signal";
  return (
    <li className="relative">
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="min-h-11 w-full border border-rule-strong bg-paper p-3 pr-9 text-left hover:bg-wash aria-pressed:border-signal aria-pressed:shadow-[inset_0_0_0_1px_var(--color-signal)]"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{symbol}</span>
          {changes.day !== null && (
            <Badge tone={changes.day >= 0 ? "gain" : "signal"}>
              {formatPercent(changes.day)}
            </Badge>
          )}
        </div>
        <div
          aria-live="polite"
          aria-atomic="true"
          className="mt-1 text-lg font-medium tabular-nums"
        >
          {quote?.error ? (
            <span className="text-signal-ink">erreur</span>
          ) : quote?.value !== undefined && quote.currency ? (
            <>
              <span>
                {quote.value.toLocaleString("fr-FR", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>{" "}
              <span className="text-xs text-muted">{quote.currency}</span>
            </>
          ) : (
            "—"
          )}
        </div>
        <div className="mt-1 flex items-end justify-between gap-2">
          <span className="text-xs text-muted">
            {quote ? formatAsOf(quote) : ""} {quote?.source ? `· ${quote.source}` : ""}
            {quote?.delayed ? " · différé" : ""}
            {changes.period !== null && (
              <>
                {" "}
                · {periodLabel} : {formatPercent(changes.period)}
              </>
            )}
          </span>
          <Sparkline
            points={points.map((point) => point.value)}
            label={`tendance de ${symbol} sur ${periodLabel}`}
            tone={sparkTone}
          />
        </div>
      </button>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Retirer ${symbol} de la liste`}
        className="absolute right-1 top-1 flex min-h-11 min-w-11 items-center justify-center text-muted hover:text-signal-ink"
      >
        ×
      </button>
    </li>
  );
}

export default function Marche() {
  const [watchlist, setWatchlist] = useState<string[]>(loadWatchlist);
  const [selected, setSelected] = useState<string | null>(null);
  const [period, setPeriod] = useState(DEFAULT_PERIOD);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [streamError, setStreamError] = useState<string | null>(null);
  const [hasReceived, setHasReceived] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const search = useMarketSearch(searchInput);

  // Sélection par défaut : premier symbole de la watchlist.
  useEffect(() => {
    if (selected === null && watchlist.length > 0) setSelected(watchlist[0]);
  }, [watchlist, selected]);
  const activeSymbol = selected ?? watchlist[0] ?? null;
  const history = useMarketHistory(activeSymbol ?? "", period.days, activeSymbol !== null);

  function addSymbol(symbol: string) {
    setWatchlist((prev) => {
      if (prev.includes(symbol) || prev.length >= MAX_SYMBOLS) return prev;
      const next = [...prev, symbol];
      saveWatchlist(next);
      return next;
    });
    setSearchInput("");
  }

  function removeSymbol(symbol: string) {
    setWatchlist((prev) => {
      const next = prev.filter((s) => s !== symbol);
      saveWatchlist(next);
      if (selected === symbol) setSelected(next[0] ?? null);
      return next;
    });
  }

  // Le flux SSE suit la watchlist : on le relance à chaque changement.
  useEffect(() => {
    if (watchlist.length === 0) return;
    const controller = new AbortController();
    setStreamError(null);
    streamMarket(
      watchlist,
      (received) => {
        setHasReceived(true);
        setQuotes((prev) => {
          const next = { ...prev };
          for (const quote of received) next[quote.symbol] = quote;
          return next;
        });
      },
      controller.signal,
    )
      .then(() => {
        // Le serveur a fermé le flux sans qu'on l'ait demandé : les prix ne bougent plus.
        if (!controller.signal.aborted) {
          setStreamError(
            "Flux de prix interrompu : les prix affichés ne sont plus mis à jour.",
          );
        }
      })
      .catch((err: unknown) => {
        if (!isAbortError(err)) {
          setStreamError(err instanceof Error ? err.message : "Erreur inconnue");
        }
      });
    return () => controller.abort();
  }, [watchlist]);

  const streamState = streamError ? "interrupted" : hasReceived ? "live" : "connecting";

  return (
    <section aria-labelledby="marche-title">
      <PageHeader
        id="marche-title"
        title="Marché"
        subtitle="Prix poussés en direct par le serveur (SSE) — le navigateur n'appelle jamais les API de marché."
        actions={
          streamState === "live" ? (
            <Badge tone="gain">Flux en direct</Badge>
          ) : streamState === "interrupted" ? (
            <Badge tone="signal">Flux interrompu</Badge>
          ) : (
            <Badge>Connexion au flux…</Badge>
          )
        }
      />
      {streamError && <ErrorNotice className="mb-3">{streamError}</ErrorNotice>}

      <form
        className="mb-3"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const first = search.data?.[0];
          if (first) addSymbol(first.symbol);
        }}
      >
        <label htmlFor="market-search" className="sr-only">
          Rechercher une entreprise ou un symbole
        </label>
        <input
          id="market-search"
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Rechercher une entreprise (ex. Apple, SAP, Bitcoin)…"
          maxLength={30}
          autoComplete="off"
          className="min-h-11 w-full border border-rule-strong bg-paper px-3 py-2 placeholder:text-muted"
        />
        {searchInput.trim().length >= 2 && (
          <ul aria-label="Suggestions" className="mt-1 border border-rule bg-paper">
            {search.isPending && (
              <li className="px-3 py-2 text-muted">Recherche…</li>
            )}
            {search.isError && (
              <li className="px-3 py-2 text-signal-ink">{search.error.message}</li>
            )}
            {search.data?.map((hit) => (
              <li key={`${hit.source}:${hit.symbol}`}>
                <button
                  type="button"
                  onClick={() => addSymbol(hit.symbol)}
                  className="flex min-h-11 w-full items-baseline justify-between gap-2 px-3 py-2 text-left hover:bg-wash"
                >
                  <span className="font-medium">{hit.symbol}</span>
                  <span className="text-xs text-muted">
                    {hit.description} · {hit.source}
                  </span>
                </button>
              </li>
            ))}
            {search.data && search.data.length === 0 && (
              <li className="px-3 py-2 text-muted">Aucun résultat.</li>
            )}
          </ul>
        )}
      </form>

      {watchlist.length === 0 ? (
        <EmptyState
          className="mb-3"
          title="Aucun symbole suivi"
          hint="Cherche une entreprise ci-dessus pour l'ajouter à ta liste."
        />
      ) : (
        <ul className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {watchlist.map((symbol) => (
            <SymbolCard
              key={symbol}
              symbol={symbol}
              quote={quotes[symbol]}
              selected={activeSymbol === symbol}
              days={period.days}
              periodLabel={period.label}
              onSelect={() => setSelected(symbol)}
              onRemove={() => removeSymbol(symbol)}
            />
          ))}
        </ul>
      )}
      <div role="group" aria-label="Période du graphique" className="mb-3 flex flex-wrap gap-2">
        {PERIODS.map((onePeriod) => (
          <button
            key={onePeriod.days}
            type="button"
            aria-pressed={period.days === onePeriod.days}
            onClick={() => setPeriod(onePeriod)}
            className="min-h-11 border border-rule-strong bg-paper px-3 py-1 font-medium hover:bg-wash aria-pressed:border-signal aria-pressed:text-signal-ink"
          >
            {onePeriod.label}
          </button>
        ))}
      </div>
      {activeSymbol !== null && (
        <Module title={activeSymbol}>
          {history.isPending && <Loading label="Chargement de l'historique…" />}
          {history.isError && <ErrorNotice>{history.error.message}</ErrorNotice>}
          {history.data && history.data.points.length === 0 && (
            <p className="text-muted">Aucun historique disponible pour ce symbole.</p>
          )}
          {history.data && history.data.points.length > 0 && (
            <>
              <PriceChart
                symbol={activeSymbol}
                source={history.data.source ?? "inconnue"}
                points={history.data.points}
                days={period.days}
              />
              <p className="mt-2 text-xs text-muted">
                Cours de clôture journaliers · source : {history.data.source ?? "inconnue"} ·
                devise : {history.data.currency ?? "inconnue"}
                {history.data.delayed ? " · différé" : ""}
              </p>
            </>
          )}
        </Module>
      )}
    </section>
  );
}
