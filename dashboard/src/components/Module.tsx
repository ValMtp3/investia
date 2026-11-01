import { useId, type ReactNode } from "react";

interface ModuleProps {
  title: string;
  children: ReactNode;
  className?: string;
}

/** Bloc encadré d'un filet fin, avec son titre dans un onglet rouge. */
export default function Module({ title, children, className = "" }: ModuleProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={`border border-rule bg-paper ${className}`}>
      <h2
        id={headingId}
        className="inline-block bg-signal px-2 py-0.5 text-xs font-bold text-paper"
      >
        {title}
      </h2>
      <div className="p-3">{children}</div>
    </section>
  );
}
