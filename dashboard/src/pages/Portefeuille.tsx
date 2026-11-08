import {
  isPortfolioPayload,
  useAdjustments,
  useBacktest,
  useOrders,
  usePortfolio,
  type Portfolio,
  type Position,
} from "../api";
import BacktestChart from "../components/BacktestChart";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import ErrorNotice from "../components/ErrorNotice";
import Loading from "../components/Loading";
import Module from "../components/Module";
import PageHeader from "../components/PageHeader";
import Stat from "../components/Stat";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";

/** Plus-value latente d'une position : valeur actuelle − coût d'achat. */
function unrealizedPnL(position: Position): { eur: number; pct: number } {
  const cost = position.quantity * position.avg_price;
  const eur = position.value_eur - cost;
  return { eur, pct: cost !== 0 ? (eur / cost) * 100 : 0 };
}

/** Date AAAA-MM-JJ → « 30/10/2026 » (sans passer par le fuseau horaire). */
function formatDay(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Barre de répartition cash / positions (CSS pur, zéro dépendance). */
function AllocationBar({ portfolio }: { portfolio: Portfolio }) {
  const total = portfolio.total_value;
  if (!(total > 0)) return null;
  const cashPct = (portfolio.cash / total) * 100;
  const positionsPct = (portfolio.positions_value / total) * 100;
  const formatPct = (value: number) =>
    value.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return (
    <div>
      <div
        role="img"
        aria-label={`Répartition du portefeuille : cash ${formatPct(cashPct)} %, positions ${formatPct(positionsPct)} %`}
        className="flex h-3 w-full border border-rule"
      >
        <div className="bg-rule-strong" style={{ width: `${cashPct}%` }} />
        <div className="bg-signal" style={{ width: `${positionsPct}%` }} />
      </div>
      <p className="mt-1 text-xs text-muted">
        Cash {formatPct(cashPct)} % · Positions {formatPct(positionsPct)} %
      </p>
    </div>
  );
}

export default function Portefeuille() {
  const { data, isLoading, isError, error } = usePortfolio();
  const orders = useOrders();
  const adjustments = useAdjustments();
  const backtest = useBacktest();

  // Garde-fou : on n'affiche un portefeuille que si le payload a la forme attendue.
  const portfolio = data != null && isPortfolioPayload(data) ? data : null;
  const malformed = data != null && !isPortfolioPayload(data);

  // Performance depuis le capital de départ (champ initial_capital, étape 7).
  const perf =
    portfolio && portfolio.initial_capital
      ? {
          eur: portfolio.total_value - portfolio.initial_capital,
          pct:
            portfolio.initial_capital !== 0
              ? ((portfolio.total_value - portfolio.initial_capital) / portfolio.initial_capital) *
                100
              : 0,
        }
      : null;

  return (
    <section aria-labelledby="portefeuille-title">
      <PageHeader
        id="portefeuille-title"
        title="Portefeuille simulé"
        subtitle="Argent fictif — aucun ordre réel. Valorisé au dernier prix connu, source affichée."
      />
      {isLoading && <Loading label="Chargement du portefeuille…" />}
      {isError && (
        <ErrorNotice>
          Erreur : {error instanceof Error ? error.message : "API indisponible"}
        </ErrorNotice>
      )}
      {malformed && (
        <ErrorNotice>Portefeuille indisponible : réponse malformée.</ErrorNotice>
      )}
      {portfolio && (
        <>
          <div className="grid gap-3 lg:grid-cols-[20rem_1fr]">
            <Module title="Valeur">
              <div className="flex flex-wrap gap-x-6 gap-y-3">
                <Stat
                  label="Valeur totale"
                  value={formatMoney(portfolio.total_value, portfolio.currency)}
                />
                {perf && (
                  <Stat
                    label="Depuis le départ"
                    value={formatMoney(perf.eur, portfolio.currency)}
                    delta={formatPercent(perf.pct)}
                    deltaTone={perf.pct >= 0 ? "gain" : "signal"}
                    source={`capital de départ : ${formatMoney(portfolio.initial_capital ?? 0, portfolio.currency)}`}
                  />
                )}
                <Stat label="Cash" value={formatMoney(portfolio.cash, portfolio.currency)} />
                <Stat
                  label="Positions"
                  value={formatMoney(portfolio.positions_value, portfolio.currency)}
                />
              </div>
              <div className="mt-3">
                <AllocationBar portfolio={portfolio} />
              </div>
            </Module>
            <Module title="Positions" className="min-w-0">
              {portfolio.positions.length === 0 ? (
                <EmptyState
                  title="Aucune position pour l'instant."
                  hint="Demande à l'agent de simuler un ordre depuis la page Agent."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <caption className="sr-only">Positions du portefeuille</caption>
                    <thead>
                      <tr className="border-b border-rule text-xs uppercase tracking-wide text-muted">
                        <th scope="col" className="px-2 py-2 font-medium">
                          Symbole
                        </th>
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          Qté
                        </th>
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          Prix moy.
                        </th>
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          Prix
                        </th>
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          Valeur
                        </th>
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          +/-
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {portfolio.positions.map((p) => {
                        const pnl = unrealizedPnL(p);
                        return (
                          <tr key={p.symbol} className="border-b border-rule hover:bg-wash">
                            <td className="px-2 py-2 font-medium">{p.symbol}</td>
                            <td className="px-2 py-2 text-right">{p.quantity}</td>
                            <td className="px-2 py-2 text-right whitespace-nowrap">
                              {formatMoney(p.avg_price, portfolio.currency)}
                            </td>
                            <td className="px-2 py-2 text-right">
                              <span className="whitespace-nowrap">
                                {formatMoney(p.price_eur, portfolio.currency)}
                              </span>{" "}
                              <span className="text-xs text-muted">({p.source})</span>
                            </td>
                            <td className="px-2 py-2 text-right font-medium whitespace-nowrap">
                              {formatMoney(p.value_eur, portfolio.currency)}
                            </td>
                            <td className="px-2 py-2 text-right whitespace-nowrap">
                              <span
                                className={
                                  pnl.eur >= 0 ? "text-gain" : "text-signal-ink"
                                }
                              >
                                {formatMoney(pnl.eur, portfolio.currency)}
                              </span>{" "}
                              <span className="text-xs text-muted">
                                ({formatPercent(pnl.pct)})
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Module>
          </div>

          <Module title="Backtest vs indice" className="mt-3 min-w-0">
            {backtest.isPending && <Loading label="Calcul du backtest…" />}
            {backtest.isError && (
              <ErrorNotice>
                Erreur :{" "}
                {backtest.error instanceof Error ? backtest.error.message : "API indisponible"}
              </ErrorNotice>
            )}
            {backtest.data &&
              (backtest.data.points.length === 0 ? (
                <EmptyState
                  title="Aucun ordre simulé pour l'instant."
                  hint="Le backtest démarre au premier ordre : demande à l'agent d'en simuler un depuis la page Agent."
                />
              ) : (
                <div>
                  <ul
                    aria-label="Performances du backtest"
                    className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm"
                  >
                    <li className="flex items-center gap-2">
                      Portefeuille
                      <Badge tone={backtest.data.perf_portfolio_pct >= 0 ? "gain" : "signal"}>
                        {formatPercent(backtest.data.perf_portfolio_pct)}
                      </Badge>
                    </li>
                    <li className="flex items-center gap-2">
                      {backtest.data.benchmark_symbol} (buy &amp; hold)
                      <Badge tone={backtest.data.perf_benchmark_pct >= 0 ? "gain" : "signal"}>
                        {formatPercent(backtest.data.perf_benchmark_pct)}
                      </Badge>
                    </li>
                  </ul>
                  <p className="mb-2 text-xs text-muted">
                    depuis le{" "}
                    {backtest.data.start_date ? formatDay(backtest.data.start_date) : "—"} ·
                    capital de départ : {formatMoney(backtest.data.initial_capital, "EUR")}
                  </p>
                  <BacktestChart
                    points={backtest.data.points}
                    benchmarkSymbol={backtest.data.benchmark_symbol}
                  />
                  {backtest.data.warnings.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-xs text-muted">
                      {backtest.data.warnings.map((warning, i) => (
                        <li key={i}>{warning}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
          </Module>

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <Module title="Ordres simulés" className="min-w-0">
              {orders.isPending && <Loading label="Chargement des ordres…" />}
              {orders.isError && (
                <ErrorNotice>
                  Erreur :{" "}
                  {orders.error instanceof Error ? orders.error.message : "API indisponible"}
                </ErrorNotice>
              )}
              {orders.data &&
                (orders.data.orders.length === 0 ? (
                  <EmptyState
                    title="Aucun ordre simulé pour l'instant."
                    hint="Les ordres validés dans la page Agent apparaissent ici."
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <caption className="sr-only">Historique des ordres simulés</caption>
                      <thead>
                        <tr className="border-b border-rule text-xs uppercase tracking-wide text-muted">
                          <th scope="col" className="px-2 py-2 font-medium">
                            Date
                          </th>
                          <th scope="col" className="px-2 py-2 font-medium">
                            Symbole
                          </th>
                          <th scope="col" className="px-2 py-2 font-medium">
                            Côté
                          </th>
                          <th scope="col" className="px-2 py-2 text-right font-medium">
                            Qté
                          </th>
                          <th scope="col" className="px-2 py-2 text-right font-medium">
                            Prix
                          </th>
                          <th scope="col" className="px-2 py-2 text-right font-medium">
                            Frais
                          </th>
                          <th scope="col" className="px-2 py-2 font-medium">
                            Statut
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {orders.data.orders.map((order) => (
                          <tr key={order.id} className="border-b border-rule hover:bg-wash">
                            <td className="px-2 py-2 whitespace-nowrap text-muted">
                              {formatDateTime(order.created_at)}
                            </td>
                            <td className="px-2 py-2 font-medium">{order.symbol}</td>
                            <td className="px-2 py-2">
                              {order.side === "buy" ? "achat" : "vente"}
                            </td>
                            <td className="px-2 py-2 text-right">{order.quantity}</td>
                            <td className="px-2 py-2 text-right whitespace-nowrap">
                              {formatMoney(order.price, "EUR")}
                            </td>
                            <td className="px-2 py-2 text-right whitespace-nowrap">
                              {formatMoney(order.fee, "EUR")}
                            </td>
                            <td className="px-2 py-2">
                              <Badge tone="neutral">
                                {order.status === "simulated" ? "simulé" : order.status}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
            </Module>

            <Module title="Ajustements de capital" className="min-w-0">
              {adjustments.isPending && <Loading label="Chargement des ajustements…" />}
              {adjustments.isError && (
                <ErrorNotice>
                  Erreur :{" "}
                  {adjustments.error instanceof Error
                    ? adjustments.error.message
                    : "API indisponible"}
                </ErrorNotice>
              )}
              {adjustments.data &&
                (adjustments.data.adjustments.length === 0 ? (
                  <EmptyState title="Aucun ajustement pour l'instant." />
                ) : (
                  <ul className="divide-y divide-rule">
                    {adjustments.data.adjustments.map((adjustment) => (
                      <li
                        key={adjustment.id}
                        className="flex items-baseline justify-between gap-3 py-2"
                      >
                        <span className="text-muted [overflow-wrap:anywhere]">
                          {formatDateTime(adjustment.created_at)} · {adjustment.reason}
                        </span>
                        <span
                          className={`font-medium tabular-nums whitespace-nowrap ${adjustment.amount >= 0 ? "text-gain" : "text-signal-ink"}`}
                        >
                          {adjustment.amount >= 0 ? "+" : ""}
                          {formatMoney(adjustment.amount, "EUR")}
                        </span>
                      </li>
                    ))}
                  </ul>
                ))}
            </Module>
          </div>
        </>
      )}
    </section>
  );
}
