"""Pont DeepEval (spec 14a) — métrique externe de tool-calling, en complément
des métriques en code (`evals/metrics.py` reste la source de vérité).

deepeval est une dev-dependance : imports lazy, aucune dépendance en prod.
`ToolCorrectnessMetric` ne fait aucun appel LLM (la clé par défaut exigée par
le constructeur n'est jamais utilisée) ; les métriques LLM-as-judge (G-Eval)
restent réservées au mode live.
"""

from investia.agent.loop import AgentResult
from investia.evals.runner import EvalCase


def to_llm_test_case(case: EvalCase, result: AgentResult):
    """Convertit (cas, résultat d'agent) en LLMTestCase deepeval."""
    from deepeval.test_case import LLMTestCase, ToolCall

    return LLMTestCase(
        input=case.question,
        actual_output=result.answer,
        expected_tools=(
            [ToolCall(name=case.expected_tool)] if case.expected_tool else []
        ),
        tools_called=[
            ToolCall(name=call.tool, input_parameters=dict(call.arguments))
            for call in result.tool_calls
        ],
    )


def deepeval_tool_correctness(case: EvalCase, result: AgentResult) -> float:
    """Score deepeval ToolCorrectness (0.0-1.0), déterministe, sans appel LLM."""
    from deepeval.metrics import ToolCorrectnessMetric

    metric = ToolCorrectnessMetric()
    metric.measure(to_llm_test_case(case, result), _show_indicator=False)
    score = metric.score
    return float(score) if score is not None else 0.0
