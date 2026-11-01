import type { ReactNode } from "react";

interface ErrorNoticeProps {
  children: ReactNode;
  className?: string;
}

/** Message d'erreur lisible : bordure complète fine, texte foncé (pas de couleur seule). */
export default function ErrorNotice({ children, className = "" }: ErrorNoticeProps) {
  return (
    <p
      role="alert"
      className={`border border-signal bg-signal-wash px-3 py-2 font-medium text-signal-ink ${className}`}
    >
      {children}
    </p>
  );
}
