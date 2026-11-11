"""Tests du runner d'evals (métriques en code, mock déterministe, zéro réseau)."""

import json
from datetime import UTC, datetime

from investia.agent import AgentResult, run_agent
from investia.agent.loop import ToolCallLog
from investia.agent.reasoning import Plan, PlanStep, ReflectionDecision
from investia.evals.metrics import compute_metrics
from investia.evals.runner import EvalCase, MockLlm, load_cases, run_evals
from investia.market.base import MarketData

FINAL_OK = """## Thèse
Le prix est 344.63 $ (source : finnhub).

## Risques
volatilité.

## Confiance
80

## Sources
- finnhub

Simulation — pas un conseil en investissement.
"""


class FakeMarket:
    async def get_quote(self, symbol):
        return MarketData(
            value=344.63,
            currency="USD",
            source="finnhub",
            timestamp=datetime(2026, 10, 31, tzinfo=UTC),
        )

    async def get_history(self, symbol, days=30):
        return []

    async def get_news(self, symbol, limit=5):
        return []


def make_case(case_id="prix-aapl", expected_tool="get_quote", final=FINAL_OK):
    return EvalCase(
        id=case_id,
        question="prix de AAPL ?",
        expected_tool=expected_tool,
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=final,
    )


async def test_metrics_tool_used_and_numbers_sourced():
    llm = MockLlm(make_case())
    from investia.tools import build_tools

    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    metrics = compute_metrics(result, expected_tool="get_quote")
    assert metrics["tool_used"] == 1.0
    assert metrics["numbers_sourced"] == 1.0
    assert metrics["format_ok"] == 1.0
    assert metrics["turns"] == 2.0


async def test_metrics_detect_wrong_tool_and_invented_number():
    case = make_case(expected_tool="get_news")  # mauvais outil attendu
    llm = MockLlm(case)
    from investia.tools import build_tools

    result = await run_agent("prix de AAPL ?", llm, build_tools(FakeMarket()))
    metrics = compute_metrics(result, expected_tool=case.expected_tool)
    assert metrics["tool_used"] == 0.0

    bad_final = FINAL_OK.replace("344.63", "999999")
    case_bad = make_case(final=bad_final)
    llm2 = MockLlm(case_bad)
    result2 = await run_agent(
        "prix ?", llm2, build_tools(FakeMarket()), max_corrections=0
    )
    metrics2 = compute_metrics(result2, expected_tool="get_quote")
    assert metrics2["numbers_sourced"] == 0.0


async def test_run_evals_returns_scores_for_every_case_and_metric():
    cases = [make_case("prix-aapl"), make_case("prix-btc", expected_tool="get_quote")]
    # le 2e cas attend le mauvais outil -> tool_used = 0
    cases[1] = make_case("prix-btc", expected_tool="get_news")
    summary = await run_evals(cases, market=FakeMarket(), mode="mock")
    assert len(summary["results"]) == 2
    first = summary["results"][0]
    assert first["case_id"] == "prix-aapl"
    assert first["metrics"]["tool_used"] == 1.0
    second = summary["results"][1]
    assert second["metrics"]["tool_used"] == 0.0


async def test_run_evals_passes_portfolio_service_to_build_tools(monkeypatch):
    """Spec 4.6 : le runner d'evals transmet le service portefeuille à build_tools."""
    import investia.evals.runner as runner

    captured: list[dict] = []
    real_build_tools = runner.build_tools

    def spy(market, **kwargs):
        captured.append(kwargs)
        return real_build_tools(market, **kwargs)

    monkeypatch.setattr(runner, "build_tools", spy)

    class FakePortfolioService:
        async def get_portfolio(self):
            return {"cash": 10_000.0, "positions": [], "currency": "EUR"}

    service = FakePortfolioService()
    await run_evals(
        [make_case()], market=FakeMarket(), mode="mock", portfolio_service=service
    )
    assert captured[-1]["portfolio_service"] is service

    await run_evals([make_case()], market=FakeMarket(), mode="mock")
    assert captured[-1]["portfolio_service"] is None


# --- Étape 12a : métrique plan_suivi ---


def test_plan_suivi_ok_quand_outils_dans_le_plan():
    result = AgentResult(
        answer="x",
        turns=2,
        tool_calls=[ToolCallLog(tool="get_quote", arguments={}, ok=True)],
        plan=Plan(steps=[PlanStep(step="prix AAPL", tool="get_quote")]),
    )
    assert compute_metrics(result, "get_quote")["plan_suivi"] == 1.0


def test_plan_suivi_zero_quand_outil_hors_plan():
    result = AgentResult(
        answer="x",
        turns=2,
        tool_calls=[ToolCallLog(tool="get_news", arguments={}, ok=True)],
        plan=Plan(steps=[PlanStep(step="prix AAPL", tool="get_quote")]),
    )
    assert compute_metrics(result, "get_news")["plan_suivi"] == 0.0


def test_plan_suivi_un_sans_plan_ou_plan_vide():
    sans_plan = AgentResult(answer="x", turns=1)
    assert compute_metrics(sans_plan, None)["plan_suivi"] == 1.0
    plan_vide = AgentResult(answer="x", turns=1, plan=Plan())
    assert compute_metrics(plan_vide, None)["plan_suivi"] == 1.0


def test_metrics_reflexion_et_auto_corrections():
    sans = AgentResult(answer="x", turns=1)
    m = compute_metrics(sans, None)
    assert m["reflexion"] == 0.0
    assert m["auto_corrections"] == 0.0

    avec_ok = AgentResult(
        answer="x", turns=2, reflections=[ReflectionDecision(ok=True)]
    )
    m = compute_metrics(avec_ok, None)
    assert m["reflexion"] == 1.0
    assert m["auto_corrections"] == 0.0

    avec_ko = AgentResult(
        answer="x",
        turns=3,
        reflections=[
            ReflectionDecision(ok=False, problemes=["chiffre non sourcé"]),
            ReflectionDecision(ok=True),
        ],
    )
    m = compute_metrics(avec_ko, None)
    assert m["reflexion"] == 1.0
    assert m["auto_corrections"] == 1.0


def test_metrics_consensus():
    import pytest

    defaut = AgentResult(answer="x", turns=1)
    assert compute_metrics(defaut, None)["consensus"] == 1.0
    k3 = AgentResult(answer="x", turns=2, consensus=2 / 3)
    assert compute_metrics(k3, None)["consensus"] == pytest.approx(2 / 3)


def test_metrics_safety_llm():
    from investia.agent.loop import GuardrailDecision

    sans = AgentResult(answer="x", turns=1)
    m = compute_metrics(sans, None)
    assert m["safety_llm_ok"] == 1.0  # non exécuté = neutre
    assert m["safety_logprobs_ok"] == 1.0

    bloque = AgentResult(
        answer="x",
        turns=2,
        guardrails=[
            GuardrailDecision(check="safety_llm", ok=False, detail="unsafe"),
            GuardrailDecision(check="safety_logprobs", ok=True, detail=""),
        ],
    )
    m = compute_metrics(bloque, None)
    assert m["safety_llm_ok"] == 0.0
    assert m["safety_logprobs_ok"] == 1.0


def test_load_cases_from_yaml(tmp_path):
    yaml_content = """
cases:
  - id: prix-aapl
    question: "prix de AAPL ?"
    expected_tool: get_quote
    mock_tool_call: {name: get_quote, arguments: {symbol: AAPL}}
    mock_final: "réponse mock"
"""
    path = tmp_path / "cases.yaml"
    path.write_text(yaml_content)
    cases = load_cases(path)
    assert len(cases) == 1
    assert cases[0].id == "prix-aapl"
    assert cases[0].expected_tool == "get_quote"


# --- Étape 12a : cas d'evals avec mock_plan ---

FINAL_SANS_CHIFFRE = """## Thèse
Aucune actualité disponible pour l'instant (source : mock).

## Risques
volatilité.

## Confiance
60

## Sources
- mock

Simulation — pas un conseil en investissement.
"""


def test_load_cases_avec_mock_plan(tmp_path):
    yaml_content = """
cases:
  - id: plan-suivi
    question: "prix de AAPL ?"
    expected_tool: get_quote
    mock_plan: '{"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}'
    mock_tool_call: {name: get_quote, arguments: {symbol: AAPL}}
    mock_final: "réponse mock"
"""
    path = tmp_path / "cases.yaml"
    path.write_text(yaml_content)
    cases = load_cases(path)
    assert cases[0].mock_plan is not None
    assert "get_quote" in cases[0].mock_plan


async def test_run_evals_plan_suivi_et_non_suivi():
    case_suivi = EvalCase(
        id="plan-suivi",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_plan=json.dumps({"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}),
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_OK,
    )
    case_non_suivi = EvalCase(
        id="plan-non-suivi",
        question="actus de AAPL ?",
        expected_tool="get_news",
        mock_plan=json.dumps({"steps": [{"step": "prix AAPL", "tool": "get_quote"}]}),
        mock_tool_call={"name": "get_news", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_SANS_CHIFFRE,
    )
    summary = await run_evals(
        [case_suivi, case_non_suivi], market=FakeMarket(), mode="mock"
    )
    by_id = {r["case_id"]: r["metrics"] for r in summary["results"]}
    assert by_id["plan-suivi"]["plan_suivi"] == 1.0
    assert by_id["plan-suivi"]["tool_used"] == 1.0
    assert by_id["plan-non-suivi"]["plan_suivi"] == 0.0
    assert by_id["plan-non-suivi"]["tool_used"] == 1.0


# --- Étape 12b : cas d'evals avec mock_responses (séquence ordonnée) ---


async def test_run_evals_reflexion_ok_et_corrige():
    final_bogueux = FINAL_OK.replace("344.63", "999999")
    case_ok = EvalCase(
        id="reflexion-ok",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=[
            {"tool_call": {"name": "get_quote", "arguments": {"symbol": "AAPL"}}},
            FINAL_OK,
            '{"ok": true, "problemes": []}',
        ],
        reasoning="reflect",
    )
    case_ko = EvalCase(
        id="reflexion-corrige",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=[
            {"tool_call": {"name": "get_quote", "arguments": {"symbol": "AAPL"}}},
            final_bogueux,
            '{"ok": false, "problemes": ["chiffre 999999 non sourcé"]}',
            FINAL_OK,
            '{"ok": true, "problemes": []}',
        ],
        reasoning="reflect",
    )
    summary = await run_evals([case_ok, case_ko], market=FakeMarket(), mode="mock")
    by_id = {r["case_id"]: r["metrics"] for r in summary["results"]}
    assert by_id["reflexion-ok"]["reflexion"] == 1.0
    assert by_id["reflexion-ok"]["auto_corrections"] == 0.0
    assert by_id["reflexion-ok"]["tool_used"] == 1.0
    assert by_id["reflexion-corrige"]["reflexion"] == 1.0
    assert by_id["reflexion-corrige"]["auto_corrections"] == 1.0
    assert by_id["reflexion-corrige"]["tool_used"] == 1.0


async def test_mock_responses_accepte_le_format_yaml_content_en_dict():
    """Depuis le YAML, chaque contenu arrive sous forme {'content': '...'} (12b)."""
    case = EvalCase(
        id="reflexion-dict",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=[
            {"tool_call": {"name": "get_quote", "arguments": {"symbol": "AAPL"}}},
            {"content": FINAL_OK.replace("344.63", "999999")},
            {"content": '{"ok": false, "problemes": ["chiffre non sourcé"]}'},
            {"content": FINAL_OK},
            {"content": '{"ok": true, "problemes": []}'},
        ],
        reasoning="reflect",
    )
    summary = await run_evals([case], market=FakeMarket(), mode="mock")
    metrics = summary["results"][0]["metrics"]
    assert metrics["auto_corrections"] == 1.0
    assert metrics["numbers_sourced"] == 1.0


# --- Étape 12c : self-consistency, k variantes par cas ---


def _variant(content):
    return [
        {"tool_call": {"name": "get_quote", "arguments": {"symbol": "AAPL"}}},
        {"content": content},
    ]


async def test_run_evals_consensus_fort_et_unanime():
    import pytest

    variant_b = FINAL_OK.replace(
        "Le prix est 344.63 $", "L'action cote à 344.63 $"
    ).replace("## Confiance\n80", "## Confiance\n70")
    case_fort = EvalCase(
        id="consensus-fort",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        consistency_k=3,
        mock_variants=[_variant(FINAL_OK), _variant(FINAL_OK), _variant(variant_b)],
    )
    case_unanime = EvalCase(
        id="consensus-unanime",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        consistency_k=3,
        mock_variants=[_variant(FINAL_OK), _variant(FINAL_OK), _variant(FINAL_OK)],
    )
    summary = await run_evals(
        [case_fort, case_unanime], market=FakeMarket(), mode="mock"
    )
    by_id = {r["case_id"]: r["metrics"] for r in summary["results"]}
    assert by_id["consensus-fort"]["consensus"] == pytest.approx(2 / 3)
    assert by_id["consensus-fort"]["tool_used"] == 1.0
    assert by_id["consensus-unanime"]["consensus"] == 1.0


# --- Étape 12d : cas d'evals avec mock_decision / mock_logprobs ---


async def test_run_evals_safety_ok_unsafe_logprobs():
    base = {"tool_call": {"name": "get_quote", "arguments": {"symbol": "AAPL"}}}
    seq = [base, {"content": FINAL_OK}]
    case_ok = EvalCase(
        id="safety-ok",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=seq,
        mock_decision={
            "value": "safe",
            "probabilities": {"safe": 0.95, "unsafe": 0.05},
            "confidence": 0.9,
        },
    )
    case_unsafe = EvalCase(
        id="safety-unsafe",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=seq,
        mock_decision={
            "value": "unsafe",
            "probabilities": {"unsafe": 0.9, "safe": 0.1},
            "confidence": 0.95,
        },
    )
    case_logprobs = EvalCase(
        id="logprobs-unsafe",
        question="prix de AAPL ?",
        expected_tool="get_quote",
        mock_tool_call=None,
        mock_final="",
        mock_responses=seq,
        mock_logprobs={"Non": 0.98, "Oui": 0.02},
    )
    summary = await run_evals(
        [case_ok, case_unsafe, case_logprobs], market=FakeMarket(), mode="mock"
    )
    by_id = {r["case_id"]: r for r in summary["results"]}
    assert by_id["safety-ok"]["metrics"]["safety_llm_ok"] == 1.0
    assert by_id["safety-ok"]["status"] == "ok"
    assert by_id["safety-unsafe"]["metrics"]["safety_llm_ok"] == 0.0
    assert by_id["safety-unsafe"]["status"] == "blocked"
    assert by_id["logprobs-unsafe"]["metrics"]["safety_logprobs_ok"] == 0.0
    assert by_id["logprobs-unsafe"]["status"] == "blocked"


def test_metrics_cache_hit():
    from investia.agent import AgentResult

    depuis_cache = AgentResult(answer="x", turns=0, from_cache=True)
    assert compute_metrics(depuis_cache, None)["cache_hit"] == 1.0
    normal = AgentResult(answer="x", turns=2)
    assert compute_metrics(normal, None)["cache_hit"] == 0.0


async def test_run_evals_cache_hit():
    cache_answer = (
        "## Thèse\nAAPL vaut 344.63 $ (source : mock).\n\n## Risques\nvolatilité.\n\n"
        "## Confiance\n80\n\n## Sources\n- mock\n\n"
        "Simulation — pas un conseil en investissement.\n"
    )
    case_hit = EvalCase(
        id="cache-hit",
        question="prix de AAPL ?",
        expected_tool=None,
        mock_tool_call=None,
        mock_final="",
        mock_cache_hit=cache_answer,
    )
    case_miss = make_case("cache-miss")
    summary = await run_evals([case_hit, case_miss], market=FakeMarket(), mode="mock")
    by_id = {r["case_id"]: r for r in summary["results"]}
    assert by_id["cache-hit"]["metrics"]["cache_hit"] == 1.0
    assert by_id["cache-hit"]["metrics"]["turns"] == 0.0
    assert by_id["cache-hit"]["metrics"]["cost_cents"] == 0.0
    assert by_id["cache-hit"]["status"] == "ok"
    assert by_id["cache-miss"]["metrics"]["cache_hit"] == 0.0


# --- Étape 12f : outils web_search / read_pdf transmis à build_tools ---


class FakeSearcher:
    async def search(self, query, limit):
        return [
            {
                "title": "Communiqué officiel",
                "url": "https://example.com/cp",
                "snippet": "Chiffre d'affaires en hausse de 12 % au T3.",
                "source": "brave",
                "timestamp": "2026-11-08T10:00:00+00:00",
            }
        ]


class FakeReader:
    async def extract_text(self, url, max_pages):
        return "Rapport annuel : résultat net de 1,2 Md$."


async def test_run_evals_passe_web_searcher_et_pdf_reader(monkeypatch):
    import investia.evals.runner as runner

    captured: list[dict] = []
    real_build_tools = runner.build_tools

    def spy(market, **kwargs):
        captured.append(kwargs)
        return real_build_tools(market, **kwargs)

    monkeypatch.setattr(runner, "build_tools", spy)

    searcher, reader = FakeSearcher(), FakeReader()
    await run_evals(
        [make_case()],
        market=FakeMarket(),
        mode="mock",
        web_searcher=searcher,
        pdf_reader=reader,
    )
    assert captured[-1]["web_searcher"] is searcher
    assert captured[-1]["pdf_reader"] is reader

    await run_evals([make_case()], market=FakeMarket(), mode="mock")
    assert captured[-1]["web_searcher"] is None
    assert captured[-1]["pdf_reader"] is None


async def test_run_evals_cas_web_search_et_read_pdf_tool_used():
    final_web = FINAL_OK.replace("344.63 $", "12 % (source : brave)")
    final_pdf = FINAL_OK.replace("344.63 $", "1,2 Md$ (source : nutrient)")
    cas_web = EvalCase(
        id="web-search",
        question="Quelles sont les dernières actualités ?",
        expected_tool="web_search",
        mock_tool_call={
            "name": "web_search",
            "arguments": {"query": "actualité", "limit": 3},
        },
        mock_final=final_web,
    )
    cas_pdf = EvalCase(
        id="read-pdf",
        question="Que dit le rapport annuel ?",
        expected_tool="read_pdf",
        mock_tool_call={
            "name": "read_pdf",
            "arguments": {"url": "https://example.com/ra.pdf", "max_pages": 5},
        },
        mock_final=final_pdf,
    )
    summary = await run_evals(
        [cas_web, cas_pdf],
        market=FakeMarket(),
        mode="mock",
        web_searcher=FakeSearcher(),
        pdf_reader=FakeReader(),
    )
    by_id = {r["case_id"]: r for r in summary["results"]}
    assert by_id["web-search"]["metrics"]["tool_used"] == 1.0
    assert by_id["read-pdf"]["metrics"]["tool_used"] == 1.0
    assert by_id["web-search"]["status"] == "ok"
    assert by_id["read-pdf"]["status"] == "ok"


# --- Étape 12g : outil run_python transmis à build_tools ---


class FakePythonSandbox:
    async def run_code(self, code):
        return {
            "exit_code": 0,
            "stdout": "sharpe = 1.42\n",
            "stderr": "",
            "truncated": False,
        }


async def test_run_evals_passe_python_sandbox(monkeypatch):
    import investia.evals.runner as runner

    captured: list[dict] = []
    real_build_tools = runner.build_tools

    def spy(market, **kwargs):
        captured.append(kwargs)
        return real_build_tools(market, **kwargs)

    monkeypatch.setattr(runner, "build_tools", spy)

    sandbox = FakePythonSandbox()
    await run_evals(
        [make_case()], market=FakeMarket(), mode="mock", python_sandbox=sandbox
    )
    assert captured[-1]["python_sandbox"] is sandbox

    await run_evals([make_case()], market=FakeMarket(), mode="mock")
    assert captured[-1]["python_sandbox"] is None


async def test_run_evals_cas_run_python_tool_used():
    final = FINAL_OK.replace("344.63 $", "1.42 (source : sandbox run_python)")
    cas = EvalCase(
        id="run-python",
        question="Quel est le ratio de Sharpe de la stratégie ?",
        expected_tool="run_python",
        mock_tool_call={
            "name": "run_python",
            "arguments": {"code": "print('sharpe =', 1.42)"},
        },
        mock_final=final,
    )
    summary = await run_evals(
        [cas], market=FakeMarket(), mode="mock", python_sandbox=FakePythonSandbox()
    )
    entry = summary["results"][0]
    assert entry["metrics"]["tool_used"] == 1.0
    assert entry["status"] == "ok"


# --- Étape 12h : routeur appris — métrique routeur_choix + cas ---


def test_metrics_routeur_choix():
    result = AgentResult(answer="x", turns=1, model_key="small")
    assert compute_metrics(result, None, expected_model="small")["routeur_choix"] == 1.0
    assert compute_metrics(result, None, expected_model="large")["routeur_choix"] == 0.0
    # sans expected_model, la métrique ne pénalise pas
    assert compute_metrics(result, None)["routeur_choix"] == 1.0


async def test_run_evals_cas_routeur_learned_et_fallback():
    voisins_small = [
        {"similarity": 0.95, "model": "small", "success": True} for _ in range(6)
    ]
    case_learned = EvalCase(
        id="routeur-learned",
        question="analyse courte du prix de AAPL en deux lignes",
        expected_tool="get_quote",
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_OK,
        expected_model="small",
        mock_router_neighbors=voisins_small,
    )
    case_fallback = EvalCase(
        id="routeur-fallback",
        question="analyse approfondie de la stratégie long terme",
        expected_tool="get_quote",
        mock_tool_call={"name": "get_quote", "arguments": {"symbol": "AAPL"}},
        mock_final=FINAL_OK,
        expected_model="large",
        mock_router_neighbors=[],
    )
    summary = await run_evals(
        [case_learned, case_fallback], market=FakeMarket(), mode="mock"
    )
    by_id = {r["case_id"]: r for r in summary["results"]}
    # learned : 6 voisins small gagnent, même si les règles D44 diraient large
    assert by_id["routeur-learned"]["metrics"]["routeur_choix"] == 1.0
    assert by_id["routeur-learned"]["metrics"]["tool_used"] == 1.0
    # fallback : 0 voisin -> règles -> « analyse » -> large
    assert by_id["routeur-fallback"]["metrics"]["routeur_choix"] == 1.0
