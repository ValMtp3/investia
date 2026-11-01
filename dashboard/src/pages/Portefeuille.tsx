import { usePortfolio } from "../api";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";
import { formatMoney } from "../lib/format";

export default function Portefeuille() {
  const { data, isLoading, isError, error } = usePortfolio();

  return (
    <section aria-labelledby="portefeuille-title">
      <h1 id="portefeuille-title" className="mb-3 text-lg font-bold">
        Portefeuille simulé
      </h1>
      {isLoading && (
        <p role="status" className="text-muted">
          Chargement du portefeuille…
        </p>
      )}
      {isError && (
        <ErrorNotice>
          Erreur : {error instanceof Error ? error.message : "API indisponible"}
        </ErrorNotice>
      )}
      {data && (
        <div className="grid gap-3 lg:grid-cols-[18rem_1fr]">
          <Module title="Valeur">
            <dl className="divide-y divide-rule">
              <div className="flex items-baseline justify-between gap-3 pb-2">
                <dt className="text-muted">Valeur totale</dt>
                <dd className="text-lg font-bold">
                  {formatMoney(data.total_value, data.currency)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3 py-2">
                <dt className="text-muted">Cash</dt>
                <dd>
                  {formatMoney(data.cash, data.currency)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3 pt-2">
                <dt className="text-muted">Positions</dt>
                <dd>
                  {formatMoney(data.positions_value, data.currency)}
                </dd>
              </div>
            </dl>
          </Module>
          <Module title="Positions" className="min-w-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">Positions du portefeuille</caption>
                <thead>
                  <tr className="border-b border-rule bg-wash text-muted">
                    <th scope="col" className="px-2 py-1.5 font-medium">Symbole</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">Qté</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">Prix moy.</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">Prix</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">Valeur</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.symbol} className="border-b border-rule/50 hover:bg-wash">
                      <td className="px-2 py-1.5 font-bold">{p.symbol}</td>
                      <td className="px-2 py-1.5 text-right">{p.quantity}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap">
                        {formatMoney(p.avg_price, data.currency)}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <span className="whitespace-nowrap">{formatMoney(p.price_eur, data.currency)}</span>{" "}
                        <span className="text-xs text-muted">({p.source})</span>
                      </td>
                      <td className="px-2 py-1.5 text-right font-medium whitespace-nowrap">
                        {formatMoney(p.value_eur, data.currency)}
                      </td>
                    </tr>
                  ))}
                  {data.positions.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-2 py-4 text-center text-muted">
                        Aucune position pour l'instant.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Module>
        </div>
      )}
    </section>
  );
}
