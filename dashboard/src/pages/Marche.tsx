import { useEffect, useState } from "react";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";
import PriceChart from "../components/PriceChart";
import { streamMarket, useMarketHistory, type LiveQuote } from "../api";
import { isAbortError } from "../lib/errors";

const SYMBOLS = ["AAPL", "SAP.DE", "BTC-USD"];

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

export default function Marche() {
  const [selected, setSelected] = useState(SYMBOLS[0]);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [streamError, setStreamError] = useState<string | null>(null);
  const history = useMarketHistory(selected);

  useEffect(() => {
    const controller = new AbortController();
    setStreamError(null);
    streamMarket(
      SYMBOLS,
      (received) => {
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

  return (
    <section aria-labelledby="marche-title">
      <h1 id="marche-title" className="mb-3 text-lg font-medium">
        Marché
      </h1>
      {streamError && <ErrorNotice className="mb-3">{streamError}</ErrorNotice>}
      <ul className="mb-3 grid gap-3 sm:grid-cols-3" aria-live="polite">
        {SYMBOLS.map((symbol) => {
          const quote = quotes[symbol];
          return (
            <li key={symbol}>
              <button
                onClick={() => setSelected(symbol)}
                aria-pressed={selected === symbol}
                className="w-full border border-rule bg-paper p-3 text-left hover:bg-wash aria-pressed:border-ink aria-pressed:bg-wash aria-pressed:shadow-[inset_0_0_0_1px_var(--color-ink)]"
              >
                <div className="font-medium">{symbol}</div>
                <div className="text-lg font-medium">
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
                <div className="text-xs text-muted">
                  {quote ? formatAsOf(quote) : ""}{" "}
                  {quote?.source ? `· ${quote.source}` : ""}
                  {quote?.delayed ? " · différé" : ""}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <Module title={selected}>
        {history.isPending && (
          <p role="status" className="text-muted">
            Chargement de l'historique…
          </p>
        )}
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
