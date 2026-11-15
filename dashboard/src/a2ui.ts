// 23c : A2UI 1.0 (a2ui.org, Apache-2.0, nov 2026) — protocole agent→UI déclaratif,
// en complément d'AG-UI (21a/21b). L'agent envoie des messages JSON (surfaceUpdate,
// dataModelUpdate, beginRendering, deleteSurface) ; le client rend avec SON propre
// catalogue de composants whitelisté (A2UI_CATALOG dans A2UISurface.tsx).
// Sécurité : un composant inconnu est ignoré, jamais de HTML brut rendu.

export interface A2UIComponentDef {
  id: string;
  /** Nom dans le catalogue client (whitelist). */
  type: string;
  props?: Record<string, unknown>;
  childIds?: string[];
}

export interface A2UISurfaceModel {
  surfaceId: string;
  root: string;
  catalogId?: string;
  components: Record<string, A2UIComponentDef>;
}

export type A2UIMessage =
  | { version: string }
  | { surfaceUpdate: { surfaceId: string; components: A2UIComponentDef[] } }
  | { dataModelUpdate: { surfaceId: string; path: string; value: unknown } }
  | { beginRendering: { surfaceId: string; root: string; catalogId: string } }
  | { deleteSurface: { surfaceId: string } };

/** État des surfaces A2UI reçues sur le flux SSE (un store par run). */
export class A2UIStore {
  surfaces = new Map<string, A2UISurfaceModel>();
  version: string | null = null;

  apply(msg: A2UIMessage): void {
    if ("version" in msg) {
      this.version = msg.version;
      return;
    }
    if ("deleteSurface" in msg) {
      this.surfaces.delete(msg.deleteSurface.surfaceId);
      return;
    }
    if ("surfaceUpdate" in msg) {
      const { surfaceId, components } = msg.surfaceUpdate;
      const surface = this.surfaces.get(surfaceId) ?? {
        surfaceId,
        root: "",
        components: {},
      };
      for (const component of components) {
        surface.components[component.id] = component;
      }
      this.surfaces.set(surfaceId, surface);
      return;
    }
    if ("beginRendering" in msg) {
      const { surfaceId, root, catalogId } = msg.beginRendering;
      const surface = this.surfaces.get(surfaceId) ?? {
        surfaceId,
        root: "",
        components: {},
      };
      surface.root = root;
      surface.catalogId = catalogId;
      this.surfaces.set(surfaceId, surface);
      return;
    }
    // dataModelUpdate : pas de data-binding serveur en v1 (props littérales, comme 21b)
  }

  list(): A2UISurfaceModel[] {
    return [...this.surfaces.values()];
  }
}
