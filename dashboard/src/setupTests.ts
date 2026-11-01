import "@testing-library/jest-dom/vitest";

// jsdom n'implémente pas scrollTo (utilisé par le routeur)
window.scrollTo = () => {};

// jsdom n'a pas matchMedia (utilisé par lightweight-charts)
window.matchMedia =
  window.matchMedia ??
  ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
