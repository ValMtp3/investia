import { ColorType } from "lightweight-charts";

const MUTED_FALLBACK = "#55606a";
const GRID_COLOR = "#e1e5e8";

/** Lit `--color-muted` dans le thème ; le canvas du graphique ne sait pas lire `var(--…)`. */
function readMutedColor(): string {
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue("--color-muted")
      .trim();
    return value || MUTED_FALLBACK;
  } catch {
    return MUTED_FALLBACK;
  }
}

/** Options communes aux graphiques : texte discret, grille en filets légers. */
export function chartLayoutOptions() {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: readMutedColor(),
      fontFamily: "'Noto Sans JP', ui-sans-serif, system-ui, sans-serif",
    },
    grid: { vertLines: { color: GRID_COLOR }, horzLines: { color: GRID_COLOR } },
  };
}
