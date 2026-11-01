import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries, type IChartApi } from "lightweight-charts";
import { mockCandles, type Candle } from "../lib/mockMarket";

export default function PriceChart({ symbol }: { symbol: string }) {
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
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#0b7a43",
      downColor: "#d7261e",
      wickUpColor: "#0b7a43",
      wickDownColor: "#d7261e",
      borderVisible: false,
    });
    const data: Candle[] = mockCandles();
    series.setData(data);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [symbol]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={`Graphique fictif de ${symbol} (données de démonstration)`}
      className="w-full"
    />
  );
}
