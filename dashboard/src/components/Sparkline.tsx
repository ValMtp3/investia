interface SparklineProps {
  points: number[];
  /** Libellé d'accessibilité, ex. « tendance des 30 derniers jours de AAPL ». */
  label: string;
  tone?: "neutral" | "gain" | "signal";
  width?: number;
  height?: number;
}

const TONE_STROKE = {
  neutral: "var(--color-muted)",
  gain: "var(--color-gain)",
  signal: "var(--color-signal)",
} as const;

/** Mini-courbe SVG inline (zéro dépendance) pour une carte de prix. */
export default function Sparkline({
  points,
  label,
  tone = "neutral",
  width = 96,
  height = 28,
}: SparklineProps) {
  // Moins de 2 points ou une valeur non finie : pas de courbe fiable, on ne rend rien.
  if (points.length < 2 || !points.every((point) => Number.isFinite(point))) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;
  const stepX = width / (points.length - 1);
  const coords = points.map((point, i) => {
    const x = i * stepX;
    // span nul (cours constant) : ligne horizontale au milieu.
    const y = span === 0 ? height / 2 : height - 2 - ((point - min) / span) * (height - 4);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      preserveAspectRatio="none"
      className="block"
    >
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={TONE_STROKE[tone]}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
