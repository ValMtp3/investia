import { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { chartLayoutOptions } from "../lib/chartTheme";
import ErrorNotice from "./ErrorNotice";

export interface EvalSeriesPoint {
  time: UTCTimestamp; // secondes Unix
  value: number; // score 0..1
}

export interface EvalSeries {
  name: string;
  color: string;
  points: EvalSeriesPoint[];
}

interface EvalChartProps {
  series: EvalSeries[];
  label: string;
}

/** Courbes des scores d'evals dans le temps : une ligne par métrique. */
export default function EvalChart({ series, label }: EvalChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hasFailed, setHasFailed] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let chart: IChartApi | undefined;
    try {
      chart = createChart(container, {
        autoSize: true,
        ...chartLayoutOptions(),
      });
      for (const oneSeries of series) {
        chart.addSeries(LineSeries, { color: oneSeries.color, lineWidth: 2 }).setData(
          oneSeries.points,
        );
      }
      chart.timeScale().fitContent();
      setHasFailed(false);
    } catch {
      // lightweight-charts lève sur des données qu'il refuse (ex. deux points au même
      // instant) : on libère le graphique et on l'annonce au lieu de démonter la page.
      chart?.remove();
      setHasFailed(true);
      return;
    }
    return () => chart.remove();
  }, [series]);

  return (
    <>
      {hasFailed && (
        <ErrorNotice className="mb-2">
          Le graphique des évaluations n'a pas pu être tracé : les données reçues sont
          peut-être incohérentes.
        </ErrorNotice>
      )}
      <div
        ref={containerRef}
        role="img"
        aria-label={label}
        hidden={hasFailed}
        className="h-[260px] w-full"
      />
    </>
  );
}
