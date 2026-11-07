import { ColorType } from "lightweight-charts";

const FALLBACKS = {
  muted: "#9aa3ad",
  grid: "#23272e",
  ink: "#e8eaec",
  signal: "#d7261e",
  focus: "#5b8def",
  gain: "#2fbf71",
  caution: "#e8b339",
} as const;

/** Lit un token `--color-*` du thème ; le canvas du graphique ne sait pas lire `var(--…)`. */
function readToken(name: string, fallback: string): string {
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(`--color-${name}`)
      .trim();
    return value || fallback;
  } catch {
    return fallback;
  }
}

/** Options communes aux graphiques : fond transparent (le conteneur a sa surface),
 *  texte discret, grille en filets légers lus depuis le thème (D63). */
export function chartLayoutOptions() {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: readToken("muted", FALLBACKS.muted),
      fontFamily: "'Noto Sans JP', ui-sans-serif, system-ui, sans-serif",
    },
    grid: {
      vertLines: { color: readToken("chart-grid", FALLBACKS.grid) },
      horzLines: { color: readToken("chart-grid", FALLBACKS.grid) },
    },
  };
}

/** Couleur de la courbe de prix (token ink) et son remplissage dégradé. */
export function priceLineColor(): string {
  return readToken("ink", FALLBACKS.ink);
}

/** Remplissage de l'area sous la courbe : ink atténué en haut, transparent en bas. */
export function priceAreaColors(): { topColor: string; bottomColor: string } {
  const ink = readToken("ink", FALLBACKS.ink);
  return { topColor: `${ink}2e`, bottomColor: `${ink}00` };
}

/** Une couleur par métrique d'eval, dans l'ordre, lue depuis le thème (D63). */
export function evalSeriesColors(): string[] {
  return ["signal", "focus", "gain", "caution", "ink", "muted"].map((name, i) =>
    readToken(name, Object.values(FALLBACKS)[i % Object.values(FALLBACKS).length]),
  );
}
