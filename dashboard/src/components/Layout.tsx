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
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <span className="text-lg font-bold">Investia</span>
          <nav aria-label="Navigation principale">
            <ul className="flex gap-4">
              {NAV.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    aria-current={pathname === item.to ? "page" : undefined}
                    className="rounded px-2 py-1 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <div
        role="alert"
        className="bg-amber-500/10 text-center text-sm text-amber-300 border-b border-amber-500/30 py-1"
      >
        Simulation — argent fictif, pas un conseil en investissement.
      </div>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
