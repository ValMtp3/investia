"""Plan d'exécution multi-agents (chantier 24a, D106) : niveaux topologiques.

Chaque agent déclare ses dépendances (`requires` = champs du contexte produits
par d'autres agents) et ce qu'il produit (`produces`). `topological_levels`
groupe les agents en niveaux : tous les agents d'un même niveau peuvent tourner
en parallèle (asyncio.gather côté orchestrateur), un agent n'attend que les
niveaux précédents. Un champ requis produit par aucun agent de la sélection
est traité comme satisfait (l'agent recevra juste le champ absent, comme en
séquentiel aujourd'hui).

Un agent inconnu du registre est racine par défaut (requires vide, produit
"analysis") : on peut en ajouter sans toucher au plan.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    """Déclaration d'un agent pour le plan d'exécution."""

    name: str
    requires: tuple[str, ...] = field(default_factory=tuple)
    produces: tuple[str, ...] = field(default_factory=tuple)


# Les 3 agents historiques (6.1) : chaîne analyste -> risque -> redacteur.
# 24b : macro et news sont des agents racine (parallèles à l'analyste).
AGENT_SPECS: dict[str, AgentSpec] = {
    "analyste": AgentSpec("analyste", requires=(), produces=("analysis",)),
    "risque": AgentSpec("risque", requires=("analysis",), produces=("verdict",)),
    "redacteur": AgentSpec("redacteur", requires=("analysis", "verdict"), produces=()),
    "macro": AgentSpec("macro", requires=(), produces=("macro",)),
    "news": AgentSpec("news", requires=(), produces=("news",)),
}

# Fallback pour un agent non déclaré : racine, produit "analysis" (comme tout
# agent non-risque dans l'orchestrateur).
_DEFAULT_SPEC_PRODUCES: tuple[str, ...] = ("analysis",)


def _spec_of(name: str, specs: dict[str, AgentSpec]) -> AgentSpec:
    return specs.get(name) or AgentSpec(name, produces=_DEFAULT_SPEC_PRODUCES)


def produced_fields(
    name: str, specs: dict[str, AgentSpec] | None = None
) -> tuple[str, ...]:
    """Champs du contexte produits par l'agent `name` (fallback : "analysis")."""
    specs = specs if specs is not None else AGENT_SPECS
    return _spec_of(name, specs).produces


def topological_levels(
    agents: list[str], specs: dict[str, AgentSpec] | None = None
) -> list[list[str]]:
    """Groupe `agents` en niveaux topologiques (ordre d'entrée conservé).

    Niveau 0 = agents dont chaque champ requis est produit hors de la
    sélection ou pas encore produit ; niveau N+1 = agents dont tous les
    champs requis produits par la sélection sont dans les niveaux < N.
    Lève ValueError si aucun agent ne peut avancer (cycle de dépendances).
    """
    specs = specs if specs is not None else AGENT_SPECS
    selected = list(agents)
    produced_by_selection: set[str] = set()
    for name in selected:
        produced_by_selection.update(_spec_of(name, specs).produces)

    remaining = list(selected)
    done_fields: set[str] = set()
    levels: list[list[str]] = []
    while remaining:
        level = [
            name
            for name in remaining
            if all(
                req not in produced_by_selection or req in done_fields
                for req in _spec_of(name, specs).requires
            )
        ]
        if not level:
            raise ValueError(f"cycle de dépendances entre agents : {sorted(remaining)}")
        levels.append(level)
        for name in level:
            done_fields.update(_spec_of(name, specs).produces)
        remaining = [name for name in remaining if name not in level]
    return levels
