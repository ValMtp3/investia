// Données mock pour le squelette (le temps réel SSE arrive à l'étape 4.4).
export interface MockQuote {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  time: string;
  delayed: boolean;
}

export const MOCK_QUOTES: MockQuote[] = [
  { symbol: "AAPL", name: "Apple", price: 344.63, changePct: 1.2, time: "16:00", delayed: false },
  { symbol: "SAP.DE", name: "SAP", price: 211.25, changePct: -0.4, time: "17:30", delayed: true },
  { symbol: "BTC-USD", name: "Bitcoin", price: 69245, changePct: 2.8, time: "17:45", delayed: false },
];

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
    const day = new Date(2026, 9, 31 - i);
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
