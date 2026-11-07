import { useId, type ReactNode } from "react";

interface ModuleProps {
  title: string;
  children: ReactNode;
  className?: string;
}

/** Bloc de page : surface avec filet fin et liseré signal en haut, titre en étiquette. */
export default function Module({ title, children, className = "" }: ModuleProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={`border border-t-2 border-rule border-t-signal bg-paper ${className}`}
    >
      <h2
        id={headingId}
        className="px-3 pt-2 text-xs font-medium uppercase tracking-wide text-muted"
      >
        {title}
      </h2>
      <div className="p-3">{children}</div>
    </section>
  );
}
