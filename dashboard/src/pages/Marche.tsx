import { useEffect, useState } from "react";
import ErrorNotice from "../components/ErrorNotice";
import Badge from "../components/Badge";
import Loading from "../components/Loading";
import Module from "../components/Module";
import PageHeader from "../components/PageHeader";
import PriceChart from "../components/PriceChart";
import Sparkline from "../components/Sparkline";
import {
  streamMarket,
  useMarketHistory,
  type HistoryPoint,
  type LiveQuote,
} from "../api";
import { isAbortError } from "../lib/errors";
import { formatPercent } from "../lib/format";

/** Liste de suivi (max 20 côté backend). Les 3 premiers symboles restent ceux d'avant. */
const SYMBOLS = ["AAPL", "SAP.DE", "BTC-USD", "MSFT", "NVDA", "ETH-USD", "AIR.PA"];

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
}

/** Carte d'un symbole : prix live, variation du jour, sparkline de la période. */
function SymbolCard({ symbol, quote, selected, days, periodLabel, onSelect }: SymbolCardProps) {
  const history = useMarketHistory(symbol, days);
  const points = history.data?.points ?? [];
  const changes = pctChanges(points);
  const sparkTone =
    changes.period === null ? "neutral" : changes.period >= 0 ? "gain" : "signal";
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="min-h-11 w-full border border-rule-strong bg-paper p-3 text-left hover:bg-wash aria-pressed:border-signal aria-pressed:shadow-[inset_0_0_0_1px_var(--color-signal)]"
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
    </li>
  );
}

export default function Marche() {
  const [selected, setSelected] = useState(SYMBOLS[0]);
  const [period, setPeriod] = useState(DEFAULT_PERIOD);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [streamError, setStreamError] = useState<string | null>(null);
  const [hasReceived, setHasReceived] = useState(false);
  const history = useMarketHistory(selected, period.days);

  useEffect(() => {
    const controller = new AbortController();
    setStreamError(null);
    streamMarket(
      SYMBOLS,
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
  }, []);

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
      <ul className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SYMBOLS.map((symbol) => (
          <SymbolCard
            key={symbol}
            symbol={symbol}
            quote={quotes[symbol]}
            selected={selected === symbol}
            days={period.days}
            periodLabel={period.label}
            onSelect={() => setSelected(symbol)}
          />
        ))}
      </ul>
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
      <Module title={selected}>
        {history.isPending && <Loading label="Chargement de l'historique…" />}
        {history.isError && <ErrorNotice>{history.error.message}</ErrorNotice>}
        {history.data && history.data.points.length === 0 && (
          <p className="text-muted">Aucun historique disponible pour ce symbole.</p>
        )}
        {history.data && history.data.points.length > 0 && (
          <>
            <PriceChart
              symbol={selected}
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
    </section>
  );
}
