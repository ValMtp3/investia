interface StatProps {
  label: string;
  value: string;
  /** Variation affichée sous la valeur, ex. « +1,2 % » (couleur via deltaTone). */
  delta?: string;
  deltaTone?: "gain" | "signal";
  /** Source du chiffre, ex. « source : finnhub » (PRODUCT.md : chaque chiffre a sa source). */
  source?: string;
  className?: string;
}

/** Chiffre clé d'un tableau de bord : libellé, valeur, variation et source. */
export default function Stat({
  label,
  value,
  delta,
  deltaTone = "gain",
  source,
  className = "",
}: StatProps) {
  return (
    <div className={className}>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-medium tabular-nums">{value}</div>
      {delta && (
        <div
          className={`text-xs font-medium ${deltaTone === "signal" ? "text-signal-ink" : "text-gain"}`}
        >
          {delta}
        </div>
      )}
      {source && <div className="text-xs text-muted">{source}</div>}
    </div>
  );
}
