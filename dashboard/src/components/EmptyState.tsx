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
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="mx-auto mb-2 h-6 w-6 text-rule-strong"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <circle cx="12" cy="12" r="9" />
        <line x1="8" y1="12" x2="16" y2="12" />
      </svg>
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted [text-wrap:pretty]">{hint}</p>}
      {action && <div className="mt-3 flex justify-center gap-2">{action}</div>}
    </div>
  );
}
