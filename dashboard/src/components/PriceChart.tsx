import { useEffect, useRef, useState } from "react";
import { createChart, AreaSeries, type IChartApi } from "lightweight-charts";
import type { HistoryPoint } from "../api";
import {
  chartLayoutOptions,
  priceAreaColors,
  priceLineColor,
} from "../lib/chartTheme";
import ErrorNotice from "./ErrorNotice";

interface PriceChartProps {
  symbol: string;
  source: string;
  points: HistoryPoint[];
  /** Période affichée, reprise dans le texte alternatif (ex. 30 pour « 30 jours »). */
  days: number;
}

/** Courbe des cours de clôture journaliers d'un symbole (area, couleurs du thème). */
export default function PriceChart({ symbol, source, points, days }: PriceChartProps) {
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
      const series = chart.addSeries(AreaSeries, {
        lineColor: priceLineColor(),
        lineWidth: 2,
        ...priceAreaColors(),
      });
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
        aria-label={`Courbe des cours de clôture de ${symbol}, ${days} jours, source ${source}`}
        hidden={hasFailed}
        className="h-[300px] w-full"
      />
    </>
  );
}
