"""TDD 6.2 : chaque approche (maison + 3 frameworks) rejoue les cas mock d'evals.

Contrat : pour chaque cas de evals/cases.yaml, l'approche appelle l'outil
attendu puis produit la réponse finale mockée.
"""

from pathlib import Path

import pytest
from investia.evals.runner import MockMarket, load_cases
from investia.tools import build_tools

from impl import langgraph_impl, maison, openai_agents_impl, pydantic_ai_impl

# load_cases() calcule evals/ depuis le package installé : on passe le chemin du repo.
CASES = load_cases(Path(__file__).resolve().parents[2] / "evals" / "cases.yaml")
TOOLS = build_tools(MockMarket())

APPROACHES = [
    ("maison", maison.run_case),
    ("langgraph", langgraph_impl.run_case),
    ("pydantic-ai", pydantic_ai_impl.run_case),
    ("openai-agents", openai_agents_impl.run_case),
]


@pytest.mark.parametrize(
    "approach,run_case", APPROACHES, ids=[a for a, _ in APPROACHES]
)
async def test_every_case_calls_expected_tool_and_answers(approach, run_case):
    for case in CASES:
        outcome = await run_case(
            approach,
            case.id,
            case.question,
            case.expected_tool,
            case.mock_tool_call,
            case.mock_final,
            TOOLS,
        )
        assert outcome.error is None, f"{approach}/{case.id}: {outcome.error}"
        assert outcome.tool_called == case.expected_tool, (
            f"{approach}/{case.id}: outil appelé {outcome.tool_called}, "
            f"attendu {case.expected_tool}"
        )
        assert case.mock_final.strip()[:30] in outcome.answer, (
            f"{approach}/{case.id}: réponse inattendue: {outcome.answer[:80]}"
        )
