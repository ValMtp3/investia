// 23c : rendu d'une surface A2UI 1.0 via le catalogue whitelisté côté client.
// Un composant inconnu du catalogue est ignoré (jamais de HTML brut) — même
// règle de sécurité que la whitelist ui_component de 21b.

import type { ComponentType, ReactNode } from "react";

import type { A2UISurfaceModel } from "../a2ui";
import HistoryChart from "./HistoryChart";

/** Catalogue whitelist (23c) : seuls ces composants peuvent être instanciés. */
export const A2UI_CATALOG: Record<string, ComponentType<any>> = {
  HistoryChart,
};

const MAX_DEPTH = 8;

export default function A2UISurface({ surface }: { surface: A2UISurfaceModel }) {
  const renderComponent = (id: string, depth: number): ReactNode => {
    if (depth > MAX_DEPTH) return null;
    const component = surface.components[id];
    if (!component) return null;
    const Comp = A2UI_CATALOG[component.type];
    if (!Comp) return null; // inconnu → ignoré
    return (
      <div
        key={id}
        aria-label={`Composant ${component.type}`}
        className="mb-2 mt-1 border border-rule bg-wash/50 p-2"
      >
        <Comp {...(component.props ?? {})} />
        {(component.childIds ?? []).map((childId) => renderComponent(childId, depth + 1))}
      </div>
    );
  };
  return <>{renderComponent(surface.root, 0)}</>;
}
