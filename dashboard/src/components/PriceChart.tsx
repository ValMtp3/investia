import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineSeries, type IChartApi } from "lightweight-charts";
import { HISTORY_DAYS, type HistoryPoint } from "../api";
import ErrorNotice from "./ErrorNotice";

interface PriceChartProps {
  symbol: string;
  source: string;
  points: HistoryPoint[];
}

/** Courbe des cours de clôture journaliers d'un symbole. */
export default function PriceChart({ symbol, source, points }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hasFailed, setHasFailed] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        autoSize: true, // prend la taille du conteneur (h-[300px] ci-dessous)
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#55606a",
          fontFamily: "'Noto Sans JP', ui-sans-serif, system-ui, sans-serif",
        },
        grid: { vertLines: { color: "#e1e5e8" }, horzLines: { color: "#e1e5e8" } },
      });
      const series = chart.addSeries(LineSeries, { color: "#1b1f23", lineWidth: 2 });
      series.setData(points);
      chart.timeScale().fitContent();
      setHasFailed(false);
    } catch {
      // lightweight-charts lève une exception sur des données qu'il refuse : on libère
      // le graphique et on l'annonce, au lieu de laisser l'exception démonter la page.
      chart?.remove();
      setHasFailed(true);
      return;
    }
    return () => chart.remove();
  }, [points]);

  return (
    <>
      {hasFailed && (
        <ErrorNotice className="mb-2">
          Le graphique n'a pas pu être tracé : les données reçues sont peut-être
          incohérentes.
        </ErrorNotice>
      )}
      <div
        ref={containerRef}
        role="img"
        aria-label={`Courbe des cours de clôture de ${symbol}, ${HISTORY_DAYS} jours, source ${source}`}
        hidden={hasFailed}
        className="h-[300px] w-full"
      />
    </>
  );
}
