"""Tests TDD du LinUCBRouter (chantier 23d) — fakes en mémoire, zéro DB."""

import random
from datetime import UTC, datetime

import pytest

from investia.llm.models import ModelConfig, ModelsConfig
from investia.llm.router import Neighbor


def make_models() -> ModelsConfig:
    return ModelsConfig(
        small=ModelConfig(
            name="small-x", price_input_per_m=0.30, price_output_per_m=1.20
        ),
        large=ModelConfig(
            name="large-y", price_input_per_m=3.00, price_output_per_m=15.00
        ),
    )


class FakeFeedbackStore:
    def __init__(self, neighbors=None):
        self._neighbors = list(neighbors or [])
        self.recorded: list[tuple] = []

    async def neighbors(self, question: str, k: int = 7) -> list[Neighbor]:
        return self._neighbors[:k]

    async def record(
        self, question: str, model: str, success: bool, cost_cents: float = 0.0
    ) -> None:
        self.recorded.append((question, model, success, cost_cents))


class FakeLinUCBStore:
    def __init__(self, initial=None):
        self._initial = initial or {}
        self.saved: dict[str, dict] = {}

    async def load_all(self) -> dict[str, dict]:
        return dict(self._initial)

    async def save(self, arm: str, state: dict) -> None:
        self.saved[arm] = state


def n(similarity: float, model: str, success: bool) -> Neighbor:
    return Neighbor(similarity=similarity, model=model, success=success)


async def test_cold_start_fallback_regles():
    from investia.llm.linucb import LinUCBRouter

    router = LinUCBRouter(
        FakeFeedbackStore([n(0.9, "small", True)] * 6),
        FakeLinUCBStore(),
        models=make_models(),
        rng=random.Random(0),
    )
    model, source = await router.choose("analyse approfondie de la stratégie")
    assert source == "rules"
    assert model == "large"  # règle D44


async def test_warm_choisit_linucb_apres_min_feedbacks():
    from investia.llm.linucb import LinUCBRouter

    feedback = FakeFeedbackStore([n(0.9, "small", True)] * 6)
    state_store = FakeLinUCBStore()
    router = LinUCBRouter(
        feedback,
        state_store,
        models=make_models(),
        alpha=0.0,
        epsilon=0.0,
        rng=random.Random(0),
    )
    # 5 succès small -> le bras small a un theta positif
    for i in range(5):
        await router.record(f"question {i}", "small", True, cost_cents=1.0)
    model, source = await router.choose("question proche")
    assert source == "linucb"
    assert model == "small"


async def test_explore_avec_epsilon_1():
    from investia.llm.linucb import LinUCBRouter

    router = LinUCBRouter(
        FakeFeedbackStore(),
        FakeLinUCBStore(),
        models=make_models(),
        epsilon=1.0,
        rng=random.Random(0),
    )
    for i in range(6):
        await router.record(f"q{i}", "small", True)
    sources = set()
    for _ in range(10):
        _model, source = await router.choose("q")
        sources.add(source)
    assert sources == {"explore"}


async def test_record_ecrit_feedback_avec_cout_et_sauvegarde_le_bras():
    from investia.llm.linucb import LinUCBRouter

    feedback = FakeFeedbackStore()
    state_store = FakeLinUCBStore()
    router = LinUCBRouter(
        feedback, state_store, models=make_models(), rng=random.Random(0)
    )
    await router.record("q", "small", True, cost_cents=12.5)
    assert feedback.recorded == [("q", "small", True, 12.5)]
    assert "small" in state_store.saved  # état LinUCB persisté
    assert state_store.saved["small"]["n"] == 1


async def test_reward_succes_moins_cout():
    from investia.llm.linucb import LinUCBRouter

    # cost_weight=0.5, budget=100 : succès avec coût 50 -> reward = 1 - 0.5*0.5 = 0.75
    router = LinUCBRouter(
        FakeFeedbackStore(),
        FakeLinUCBStore(),
        models=make_models(),
        cost_weight=0.5,
        budget_cents=100.0,
        rng=random.Random(0),
    )
    await router.record("q", "small", True, cost_cents=50.0)
    b = router.linucb.state("small")["b"]
    # b = reward * x ; x[0] = 1.0 (biais) -> b[0] == reward
    assert b[0] == pytest.approx(0.75)
    # échec -> reward = 0 - ... clampé à 0
    await router.record("q2", "large", False, cost_cents=0.0)
    assert router.linucb.state("large")["b"][0] == pytest.approx(0.0)


async def test_etat_charge_depuis_le_store_au_demarrage():
    from investia.llm.linucb import LinUCB, LinUCBRouter

    warm = LinUCB(d=7, alpha=0.0, epsilon=0.0)
    x = [1.0, 0.9, 0.0, 0.1, 0.5, 1.0, 0.05]
    for _ in range(5):
        warm.update("small", x, 1.0)
    initial = {"small": warm.state("small"), "large": warm.state("large")}
    router = LinUCBRouter(
        FakeFeedbackStore(),
        FakeLinUCBStore(initial=initial),
        models=make_models(),
        alpha=0.0,
        epsilon=0.0,
        rng=random.Random(0),
    )
    model, source = await router.choose("q")
    assert source == "linucb"  # plus froid : vient du store, pas des règles
    assert model == "small"


# --- boucle : run_agent passe le coût réel au record ---------------------------

from dataclasses import replace  # noqa: E402

from test_agent_loop import (  # noqa: E402
    FINAL_WITH_PRICE,
    FakeLlm,
    FakeMarket,
    make_response,
    quote_tool_call,
)
from test_sse import FakeTraceStore  # noqa: E402

from investia.agent import run_agent  # noqa: E402
from investia.market.base import MarketData  # noqa: E402
from investia.tools import build_tools  # noqa: E402


class CostCapturingRouter:
    def __init__(self) -> None:
        self.records: list[tuple] = []

    async def choose(self, question: str):
        return "small", "linucb"

    async def record(
        self, question: str, model: str, success: bool, cost_cents: float = 0.0
    ) -> None:
        self.records.append((question, model, success, cost_cents))


async def test_run_agent_record_avec_cost_cents_du_run():
    quote = MarketData(
        value=344.63,
        currency="USD",
        source="finnhub",
        timestamp=datetime(2026, 10, 31, tzinfo=UTC),
    )
    llm = FakeLlm(
        [
            replace(
                make_response(content="je cherche", tool_calls=quote_tool_call()),
                cached_tokens=10,
            ),
            make_response(content=FINAL_WITH_PRICE),
        ]
    )
    router = CostCapturingRouter()
    result = await run_agent(
        "prix de AAPL ?",
        llm,
        build_tools(FakeMarket(quote=quote)),
        trace_store=FakeTraceStore(),
        router=router,
    )
    assert len(router.records) == 1
    _q, model, success, cost_cents = router.records[0]
    assert model == "small"
    assert success is True
    assert cost_cents == pytest.approx(result.total_cost_cents)


# --- 23d : intégration pgvector (jamais en CI) --------------------------------


@pytest.mark.integration
async def test_integration_linucb_store_roundtrip_et_feedbacks_avec_cout():
    from investia.db import get_session
    from investia.llm.linucb import LinUCB
    from investia.llm.router_store import DbLinUCBStore, DbRouterFeedback
    from investia.memory.embeddings import FakeEmbeddingsForTests

    store = DbLinUCBStore(get_session())
    linucb = LinUCB(d=7, alpha=0.3, epsilon=0.0)
    x = [1.0, 0.8, 0.1, 0.2, 0.5, 1.0, 0.05]
    for _ in range(3):
        linucb.update("small", x, 0.9)
    await store.save("small", linucb.state("small"))
    loaded = await store.load_all()
    assert loaded["small"]["n"] == 3
    assert loaded["small"]["b"][0] == pytest.approx(3 * 0.9 * x[0])
    clone = LinUCB(d=7, alpha=0.3, epsilon=0.0)
    clone.load_state("small", loaded["small"])
    assert clone.state("small")["A"] == linucb.state("small")["A"]

    feedback = DbRouterFeedback(get_session(), FakeEmbeddingsForTests())
    await feedback.record("prix AAPL ?", "small", True, cost_cents=2.5)
    all_fb = await store.all_feedbacks()
    row = next(f for f in all_fb if f["question"] == "prix AAPL ?")
    assert row["model"] == "small"
    assert row["success"] is True
    assert row["cost_cents"] == pytest.approx(2.5)
