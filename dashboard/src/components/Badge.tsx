import type { ReactNode } from "react";

interface BadgeProps {
  tone?: "neutral" | "signal" | "gain" | "caution";
  children: ReactNode;
  className?: string;
}

const TONES = {
  neutral: "border-rule-strong text-muted",
  signal: "border-signal bg-signal-wash text-signal-ink",
  gain: "border-gain text-gain",
  caution: "border-caution text-caution",
} as const;

/** Pastille d'état : le sens vient du texte, la couleur ne fait que le renforcer. */
export default function Badge({ tone = "neutral", children, className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-block border px-1.5 py-0.5 text-xs font-medium uppercase tracking-wide ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
