import { usePortfolio } from "../api";

export default function Portefeuille() {
  const { data, isLoading, isError, error } = usePortfolio();

  return (
    <section aria-labelledby="portefeuille-title">
      <h1 id="portefeuille-title" className="text-2xl font-bold mb-4">
        Portefeuille simulé
      </h1>
      {isLoading && <p role="status">Chargement du portefeuille…</p>}
      {isError && (
        <p role="alert" className="rounded border border-red-500/50 bg-red-500/10 p-3 text-red-300">
          Erreur : {error instanceof Error ? error.message : "API indisponible"}
        </p>
      )}
      {data && (
        <div className="space-y-4">
          <div className="rounded border border-slate-800 p-4">
            <div className="text-sm text-slate-400">Valeur totale</div>
            <div className="text-3xl font-bold">
              {data.total_value.toLocaleString("fr-FR", {
                style: "currency",
                currency: data.currency,
              })}
            </div>
            <div className="text-sm text-slate-400">
              Cash : {data.cash.toLocaleString("fr-FR", { style: "currency", currency: data.currency })} ·
              Positions :{" "}
              {data.positions_value.toLocaleString("fr-FR", {
                style: "currency",
                currency: data.currency,
              })}
            </div>
          </div>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Positions du portefeuille</caption>
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th scope="col" className="py-2">Symbole</th>
                <th scope="col" className="py-2">Qté</th>
                <th scope="col" className="py-2">Prix moy.</th>
                <th scope="col" className="py-2">Prix</th>
                <th scope="col" className="py-2">Valeur</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((p) => (
                <tr key={p.symbol} className="border-b border-slate-900">
                  <td className="py-2 font-semibold">{p.symbol}</td>
                  <td className="py-2">{p.quantity}</td>
                  <td className="py-2">{p.avg_price.toFixed(2)} €</td>
                  <td className="py-2">
                    {p.price_eur.toFixed(2)} €{" "}
                    <span className="text-xs text-slate-500">({p.source})</span>
                  </td>
                  <td className="py-2">{p.value_eur.toFixed(2)} €</td>
                </tr>
              ))}
              {data.positions.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-4 text-center text-slate-500">
                    Aucune position pour l'instant.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
