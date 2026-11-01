import { Link, Outlet, useRouterState } from "@tanstack/react-router";

const NAV = [
  { to: "/marche", label: "Marché" },
  { to: "/portefeuille", label: "Portefeuille" },
  { to: "/agent", label: "Agent" },
  { to: "/traces", label: "Traces & evals" },
] as const;

export default function Layout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      <div
        role="alert"
        className="sticky top-0 z-10 border-b border-rule bg-caution-wash px-4 py-1 text-center text-xs font-medium text-caution-ink"
      >
        Simulation — argent fictif, pas un conseil en investissement.
      </div>
      <div className="flex flex-1 flex-col md:flex-row">
        <aside className="border-b border-rule md:w-44 md:shrink-0 md:border-r md:border-b-0">
          <div className="px-4 py-3 text-base font-bold">Investia</div>
          <nav aria-label="Navigation principale">
            <ul className="flex flex-wrap md:flex-col">
              {NAV.map((item) => (
                <li key={item.to} className="md:border-t md:border-rule">
                  <Link
                    to={item.to}
                    aria-current={pathname === item.to ? "page" : undefined}
                    className="block px-4 py-2 font-medium hover:bg-wash aria-[current=page]:bg-ink aria-[current=page]:text-paper"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
        <main className="min-w-0 flex-1 p-3 md:p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
