import { useEffect, useState } from "react";
import PriceChart from "../components/PriceChart";
import { streamMarket, type LiveQuote } from "../api";

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
    ).catch((err: unknown) => {
      if ((err as Error).name !== "AbortError") {
        setStreamError(err instanceof Error ? err.message : "Erreur inconnue");
      }
    });
    return () => controller.abort();
  }, []);

  return (
    <section aria-labelledby="marche-title">
      <h1 id="marche-title" className="text-2xl font-bold mb-4">
        Marché
      </h1>
      {streamError && (
        <p role="alert" className="mb-4 rounded border border-red-500/50 bg-red-500/10 p-3 text-red-300">
          {streamError}
        </p>
      )}
      <ul className="mb-6 grid gap-2 sm:grid-cols-3" aria-live="polite">
        {SYMBOLS.map((symbol) => {
          const quote = quotes[symbol];
          return (
            <li key={symbol}>
              <button
                onClick={() => setSelected(symbol)}
                aria-pressed={selected === symbol}
                className="w-full rounded border border-slate-800 p-3 text-left hover:bg-slate-900 focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                <div className="font-semibold">{symbol}</div>
                <div>
                  {quote?.error ? (
                    "erreur"
                  ) : quote?.value !== undefined && quote.currency ? (
                    <>
                      <span>
                        {quote.value.toLocaleString("fr-FR", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </span>{" "}
                      <span className="text-xs text-slate-400">{quote.currency}</span>
                    </>
                  ) : (
                    "—"
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {quote?.timestamp ? formatTime(quote.timestamp) : ""}{" "}
                  {quote?.source ? `· ${quote.source}` : ""}
                  {quote?.delayed ? " · différé" : ""}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <h2 className="text-lg font-semibold mb-2">{selected}</h2>
      <PriceChart symbol={selected} />
      <p className="mt-2 text-xs text-slate-500">
        Prix en direct via le flux SSE du backend — le graphique reste sur données mock
        (historique SSE à venir).
      </p>
    </section>
  );
}
