import { useEffect, useRef } from "react";
import { createChart, ColorType, LineSeries, type IChartApi } from "lightweight-charts";
import { HISTORY_DAYS, type HistoryPoint } from "../api";

interface PriceChartProps {
  symbol: string;
  source: string;
  points: HistoryPoint[];
}

/** Courbe des cours de clôture journaliers d'un symbole. */
export default function PriceChart({ symbol, source, points }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart: IChartApi = createChart(container, {
      autoSize: true,
      height: 300,
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
    return () => chart.remove();
  }, [points]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={`Courbe des cours de clôture de ${symbol}, ${HISTORY_DAYS} jours, source ${source}`}
      className="w-full"
    />
  );
}
