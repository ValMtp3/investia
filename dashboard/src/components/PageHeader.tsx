import type { ReactNode } from "react";

interface PageHeaderProps {
  /** Id du h1 : la <section> de la page s'y rapporte via aria-labelledby. */
  id: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

/** En-tête de page : titre (h1), sous-titre optionnel et zone d'actions à droite. */
export default function PageHeader({ id, title, subtitle, actions }: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 id={id} className="text-xl font-medium [text-wrap:balance]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-muted [text-wrap:pretty]">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
