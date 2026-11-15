import { useMarketHistory } from "../api";
import PriceChart from "./PriceChart";
import Skeleton from "./Skeleton";

interface HistoryChartProps {
  symbol: string;
  days: number;
}

/** 21b : composant poussé par l'agent (generative UI) — historique d'un symbole dans le chat. */
export default function HistoryChart({ symbol, days }: HistoryChartProps) {
  const history = useMarketHistory(symbol, days);
  if (history.isPending) return <Skeleton label={`Chargement de l'historique de ${symbol}…`} />;
  if (history.isError)
    return <p className="text-sm text-muted">Historique indisponible pour {symbol}.</p>;
  const points = history.data?.points ?? [];
  if (points.length === 0)
    return <p className="text-sm text-muted">Aucun point d'historique pour {symbol}.</p>;
  return (
    <PriceChart symbol={symbol} source={history.data?.source ?? ""} points={points} days={days} />
  );
}
