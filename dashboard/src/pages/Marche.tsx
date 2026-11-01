import { useEffect, useState } from "react";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";
import PriceChart from "../components/PriceChart";
import { streamMarket, type LiveQuote } from "../api";
import { isAbortError } from "../lib/errors";

const SYMBOLS = ["AAPL", "SAP.DE", "BTC-USD"];

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? timestamp
    : date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

export default function Marche() {
  const [selected, setSelected] = useState(SYMBOLS[0]);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [streamError, setStreamError] = useState<string | null>(null);

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
      <h1 id="marche-title" className="mb-3 text-lg font-bold">
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
                <div className="font-bold">{symbol}</div>
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
                  {quote?.timestamp ? formatTime(quote.timestamp) : ""}{" "}
                  {quote?.source ? `· ${quote.source}` : ""}
                  {quote?.delayed ? " · différé" : ""}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <Module title={selected}>
        <PriceChart symbol={selected} />
        <p className="mt-2 text-xs text-muted">
          Prix en direct via le flux SSE du backend — le graphique reste sur données mock
          (historique SSE à venir).
        </p>
      </Module>
    </section>
  );
}
