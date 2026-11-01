// Données mock restantes : uniquement l'historique du graphique (le flux SSE
// pousse les prix live depuis l'étape 4.4b ; l'historique SSE arrive plus tard).
export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function mockCandles(): Candle[] {
  const candles: Candle[] = [];
  let price = 330;
  for (let i = 29; i >= 0; i--) {
    const day = new Date(Date.UTC(2026, 9, 31 - i));
    const open = price;
    const close = open + (Math.sin(i) * 4 + 1.5);
    candles.push({
      time: day.toISOString().slice(0, 10),
      open,
      high: Math.max(open, close) + 1.2,
      low: Math.min(open, close) - 1.2,
      close,
    });
    price = close;
  }
  return candles;
}
