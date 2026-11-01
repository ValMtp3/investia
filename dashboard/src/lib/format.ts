/** Montant au format français : « 12,50 € ». La devise vient toujours de l'API. */
export function formatMoney(value: number, currency: string): string {
  return value.toLocaleString("fr-FR", { style: "currency", currency });
}
