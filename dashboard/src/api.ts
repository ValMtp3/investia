// Client API : tout passe par le backend (les clés API restent côté serveur).
import { useQuery } from "@tanstack/react-query";

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  price_eur: number;
  value_eur: number;
  source: string;
  price_timestamp: string;
}

export interface Portfolio {
  cash: number;
  positions: Position[];
  positions_value: number;
  total_value: number;
  currency: string;
}

export async function fetchPortfolio(): Promise<Portfolio> {
  const response = await fetch(`${API_URL}/portfolio`);
  if (!response.ok) {
    throw new Error(`API indisponible (HTTP ${response.status})`);
  }
  return response.json() as Promise<Portfolio>;
}

export function usePortfolio() {
  return useQuery({ queryKey: ["portfolio"], queryFn: fetchPortfolio });
}
