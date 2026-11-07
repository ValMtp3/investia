import { useEffect } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";

const NAV = [
  { to: "/marche", label: "Marché" },
  { to: "/portefeuille", label: "Portefeuille" },
  { to: "/agent", label: "Agent" },
  { to: "/traces", label: "Traces & evals" },
] as const;

/** Attribution exigée par les fournisseurs de données gratuits (PRODUCT.md). */
const DATA_ATTRIBUTION =
  "Données : Finnhub · Yahoo Finance · EODHD · CoinGecko · Frankfurter (fournisseurs gratuits, attribution affichée).";

export default function Layout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  // Après chaque navigation, le focus part dans le contenu principal : au clavier,
  // on « entre » dans la page au lieu de relire toute la navigation (a11y, étape 7).
  useEffect(() => {
    document.getElementById("main-content")?.focus();
  }, [pathname]);

  return (
    <div className="flex min-h-screen flex-col bg-bg text-ink">
      <a href="#main-content" className="skip-link">
        Aller au contenu
      </a>
      <div className="sticky top-0 z-10 border-b border-rule bg-paper/95 px-4 py-1 text-center text-xs font-medium text-caution">
        Simulation — argent fictif, pas un conseil en investissement.
      </div>
      <div className="flex flex-1 flex-col md:flex-row">
        <aside className="border-b border-rule bg-paper md:w-52 md:shrink-0 md:border-r md:border-b-0">
          <div className="flex items-center gap-2 border-b border-rule px-4 py-3">
            <span aria-hidden="true" className="inline-block h-3 w-3 bg-signal" />
            <span className="text-base font-medium tracking-wide">Investia</span>
          </div>
          <nav aria-label="Navigation principale">
            <ul className="flex flex-wrap md:flex-col">
              {NAV.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    aria-current={pathname === item.to ? "page" : undefined}
                    className="block min-h-11 px-4 py-2 font-medium hover:bg-wash aria-[current=page]:bg-wash aria-[current=page]:text-ink aria-[current=page]:shadow-[inset_2px_0_0_var(--color-signal)]"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <p className="hidden border-t border-rule px-4 py-2 text-xs text-muted md:block">
            {DATA_ATTRIBUTION}
          </p>
        </aside>
        <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 p-3 focus:outline-none md:p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
