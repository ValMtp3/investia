"""Interface commune des 4 implémentations comparées (étape 6.2).

Chaque implémentation expose `run_case` avec la même signature et le même
contrat : rejouer un cas d'eval mocké (1 appel d'outil attendu, puis réponse
finale mockée) et renvoyer ce qui s'est passé (outil appelé, réponse, coût,
durée). Le harness maison sert de référence (maison.py).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseOutcome:
    """Résultat d'un cas d'eval pour une approche."""

    approach: str
    case_id: str
    answer: str = ""
    tool_called: str | None = None
    tool_ok: bool = False
    cost_cents: float = 0.0
    duration_ms: float = 0.0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def run_case(
    approach: str,
    case_id: str,
    question: str,
    expected_tool: str,
    mock_tool_call: dict[str, Any],
    mock_final: str,
    tools: dict[str, Any],
) -> CaseOutcome:
    """À surcharger : `tools` = dict name -> BaseTool investia."""
    raise NotImplementedError
