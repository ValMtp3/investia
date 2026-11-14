interface SkeletonProps {
  /** Libellé lisible par les lecteurs d'écran (role=status), masqué visuellement. */
  label: string;
  className?: string;
}

/** 20d — état de chargement : blocs pulsés + libellé accessible (sr-only). */
export default function Skeleton({ label, className = "" }: SkeletonProps) {
  return (
    <div role="status" className={className} aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="skeleton h-4 w-2/3" aria-hidden="true" />
      <div className="skeleton mt-2 h-4 w-full" aria-hidden="true" />
      <div className="skeleton mt-2 h-4 w-1/2" aria-hidden="true" />
    </div>
  );
}
