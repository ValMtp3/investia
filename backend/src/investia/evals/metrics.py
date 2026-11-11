"""Métriques d'eval calculées EN CODE (pas de LLM juge ici)."""

from investia.agent.loop import AgentResult


def compute_metrics(result: AgentResult, expected_tool: str | None) -> dict[str, float]:
    tools_used = [call.tool for call in result.tool_calls]
    guardrails = {g.check: g.ok for g in result.guardrails}
    planned = (
        {step.tool for step in result.plan.steps if step.tool}
        if result.plan is not None
        else set()
    )
    plan_suivi = (
        1.0
        if not planned or all(call.tool in planned for call in result.tool_calls)
        else 0.0
    )
    return {
        "tool_used": 1.0 if expected_tool in tools_used else 0.0,
        "numbers_sourced": 1.0 if guardrails.get("numbers", True) else 0.0,
        "format_ok": 1.0 if guardrails.get("format", True) else 0.0,
        "language_ok": 1.0 if guardrails.get("language", True) else 0.0,
        "disclaimer_ok": 1.0 if guardrails.get("disclaimer", True) else 0.0,
        "plan_suivi": plan_suivi,
        "reflexion": 1.0 if result.reflections else 0.0,
        "auto_corrections": float(sum(1 for r in result.reflections if not r.ok)),
        "turns": float(result.turns),
        "cost_cents": result.total_cost_cents,
    }
