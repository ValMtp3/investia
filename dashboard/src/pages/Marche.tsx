import { useState } from "react";
import PriceChart from "../components/PriceChart";
import { MOCK_QUOTES } from "../lib/mockMarket";

export default function Marche() {
  const [selected, setSelected] = useState(MOCK_QUOTES[0].symbol);
  return (
    <section aria-labelledby="marche-title">
      <h1 id="marche-title" className="text-2xl font-bold mb-4">
        Marché
      </h1>
      <ul className="mb-6 grid gap-2 sm:grid-cols-3">
        {MOCK_QUOTES.map((q) => (
          <li key={q.symbol}>
            <button
              onClick={() => setSelected(q.symbol)}
              aria-pressed={selected === q.symbol}
              className="w-full rounded border border-slate-800 p-3 text-left hover:bg-slate-900 focus-visible:outline-2 focus-visible:outline-sky-400"
            >
              <div className="font-semibold">{q.symbol}</div>
              <div>
                {q.price.toLocaleString("fr-FR")} €{" "}
                <span className={q.changePct >= 0 ? "text-green-400" : "text-red-400"}>
                  {q.changePct >= 0 ? "+" : ""}
                  {q.changePct} %
                </span>
              </div>
              <div className="text-xs text-slate-400">
                {q.time} {q.delayed ? "· différé" : "· temps réel"}
              </div>
            </button>
          </li>
        ))}
      </ul>
      <h2 className="text-lg font-semibold mb-2">{selected}</h2>
      <PriceChart symbol={selected} />
      <p className="mt-2 text-xs text-slate-500">
        Données mock — le flux SSE temps réel arrive à l'étape 4.4.
      </p>
    </section>
  );
}
