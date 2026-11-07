import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}

/** État vide soigné : filet en pointillés, titre, indice et action optionnels. */
export default function EmptyState({ title, hint, action, className = "" }: EmptyStateProps) {
  return (
    <div className={`border border-dashed border-rule-strong px-4 py-6 text-center ${className}`}>
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted [text-wrap:pretty]">{hint}</p>}
      {action && <div className="mt-3 flex justify-center gap-2">{action}</div>}
    </div>
  );
}
