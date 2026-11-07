"""Métriques d'eval calculées EN CODE (pas de LLM juge ici)."""

from investia.agent.loop import AgentResult


def compute_metrics(result: AgentResult, expected_tool: str | None) -> dict[str, float]:
    tools_used = [call.tool for call in result.tool_calls]
    guardrails = {g.check: g.ok for g in result.guardrails}
    return {
        "tool_used": 1.0 if expected_tool in tools_used else 0.0,
        "numbers_sourced": 1.0 if guardrails.get("numbers", True) else 0.0,
        "format_ok": 1.0 if guardrails.get("format", True) else 0.0,
        "language_ok": 1.0 if guardrails.get("language", True) else 0.0,
        "disclaimer_ok": 1.0 if guardrails.get("disclaimer", True) else 0.0,
        "turns": float(result.turns),
        "cost_cents": result.total_cost_cents,
    }
