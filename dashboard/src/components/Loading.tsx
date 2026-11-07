interface LoadingProps {
  label: string;
}

/** Indicateur de chargement standard, annoncé aux lecteurs d'écran (role=status). */
export default function Loading({ label }: LoadingProps) {
  return (
    <p role="status" className="text-muted">
      {label}
    </p>
  );
}
