/** Montant au format français : « 12,50 € ». La devise vient toujours de l'API. */
export function formatMoney(value: number, currency: string): string {
  return value.toLocaleString("fr-FR", { style: "currency", currency });
}

/** Date ISO → « 05/11/2026, 10:30 » (heure locale). Chaîne d'origine si illisible. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
