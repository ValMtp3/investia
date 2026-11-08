import { useEffect, useRef, useState } from "react";
import { createChart, LineSeries, type IChartApi } from "lightweight-charts";
import type { BacktestPoint } from "../api";
import { chartLayoutOptions, evalSeriesColors } from "../lib/chartTheme";
import ErrorNotice from "./ErrorNotice";

interface BacktestChartProps {
  points: BacktestPoint[];
  benchmarkSymbol: string;
}

/** Courbe du backtest : portefeuille (trait plein) vs indice de référence (pointillé). */
export default function BacktestChart({ points, benchmarkSymbol }: BacktestChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hasFailed, setHasFailed] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        autoSize: true, // prend la taille du conteneur (h-[300px] ci-dessous)
        ...chartLayoutOptions(),
      });
      const colors = evalSeriesColors(); // [signal, focus, gain, caution, ink, muted]
      const portfolio = chart.addSeries(LineSeries, {
        color: colors[1], // focus : la courbe du portefeuille ressort
        lineWidth: 2,
      });
      portfolio.setData(points.map((p) => ({ time: p.date, value: p.portfolio_value })));
      const benchmark = chart.addSeries(LineSeries, {
        color: colors[5], // muted : l'indice en retrait
        lineWidth: 2,
        lineStyle: 2, // dashed
      });
      benchmark.setData(points.map((p) => ({ time: p.date, value: p.benchmark_value })));
      chart.timeScale().fitContent();
      setHasFailed(false);
    } catch {
      // Comme PriceChart : on libère le graphique et on l'annonce au lieu de tout démonter.
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
        aria-label={`Courbe du portefeuille vs indice de référence ${benchmarkSymbol}, ${points.length} jours de cotation`}
        hidden={hasFailed}
        className="h-[300px] w-full"
      />
    </>
  );
}
