"""Tests TDD du cœur LinUCB (chantier 23d) — pur stdlib, zéro DB."""

import random
from datetime import UTC, datetime

import pytest

from investia.llm.models import ModelConfig, ModelsConfig

# --- fixtures modèles synthétiques --------------------------------------------


def make_models() -> ModelsConfig:
    return ModelsConfig(
        small=ModelConfig(
            name="small-x", price_input_per_m=0.30, price_output_per_m=1.20
        ),
        large=ModelConfig(
            name="large-y", price_input_per_m=3.00, price_output_per_m=15.00
        ),
    )


# --- effective_price : fenêtres plein tarif / off-peak (UTC) ------------------


def test_effective_price_plein_tarif_en_peak_lun_ven():
    from investia.llm.linucb import effective_price

    models = make_models()
    lundi_2h = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)  # lundi 02:00 UTC = peak
    assert effective_price(models.small, "small", lundi_2h) == pytest.approx(0.30)


def test_effective_price_remise_hors_peak():
    from investia.llm.linucb import effective_price

    models = make_models()
    lundi_12h = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)  # lundi 12:00 UTC = off-peak
    assert effective_price(models.small, "small", lundi_12h) == pytest.approx(0.15)
    samedi = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)  # week-end = off-peak
    assert effective_price(models.small, "small", samedi) == pytest.approx(0.15)


def test_effective_price_large_toujours_plein_tarif():
    from investia.llm.linucb import effective_price

    models = make_models()
    lundi_12h = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    assert effective_price(models.large, "large", lundi_12h) == pytest.approx(3.00)


# --- build_features : 7 dimensions ---------------------------------------------


def test_build_features_sept_dimensions_et_bornes():
    from investia.llm.linucb import FeatureContext, build_features

    models = make_models()
    ctx = FeatureContext(
        knn_small=0.9,
        knn_large=0.2,
        now=datetime(2026, 11, 16, 12, 0, tzinfo=UTC),  # off-peak -> ratio 0.5
        models=models,
        budget_cents=100.0,
        cost_estimate_cents=25.0,
    )
    x = build_features("analyse de stratégie long terme " * 30, ctx)  # > 500 car.
    assert len(x) == 7
    assert x[0] == 1.0  # biais
    assert x[1] == pytest.approx(0.9)  # knn small
    assert x[2] == pytest.approx(0.2)  # knn large
    assert x[3] == pytest.approx(1.0)  # longueur capée à 500
    assert x[4] == pytest.approx(0.5)  # prix effectif small off-peak / catalogue
    assert x[5] == pytest.approx(1.0)  # large plein tarif
    assert x[6] == pytest.approx(0.25)  # coût estimé / budget
    assert all(0.0 <= v <= 1.0 for v in x)


def test_build_features_cout_estime_cap_budget():
    from investia.llm.linucb import FeatureContext, build_features

    ctx = FeatureContext(
        knn_small=0.5,
        knn_large=0.5,
        now=datetime(2026, 11, 16, 12, 0, tzinfo=UTC),
        models=make_models(),
        budget_cents=100.0,
        cost_estimate_cents=10_000.0,  # >> budget -> capé à 1.0
    )
    x = build_features("q", ctx)
    assert x[6] == pytest.approx(1.0)


# --- LinUCB : choose / update / anti-windup ------------------------------------


def test_choose_explore_quand_epsilon_1():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=3, alpha=0.5, epsilon=1.0)
    rng = random.Random(42)
    x = [1.0, 0.5, 0.0]
    sources = {linucb.choose(x, rng)[1] for _ in range(20)}
    assert sources == {"explore"}


def test_choose_ucb_cold_start_choisit_premier_bras_symetrique():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=3, alpha=0.5, epsilon=0.0)
    rng = random.Random(42)
    arm, source = linucb.choose([1.0, 0.0, 0.0], rng)
    assert source == "linucb"
    assert arm == "small"  # ex-aequo froid -> premier bras, déterministe


def test_update_apprend_et_choose_suit():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=2, alpha=0.0, epsilon=0.0)  # alpha=0 -> pur greedy sur theta
    rng = random.Random(0)
    x = [1.0, 0.5]
    for _ in range(5):
        linucb.update("small", x, 1.0)  # small réussit toujours
        linucb.update("large", x, 0.0)  # large échoue toujours
    arm, source = linucb.choose(x, rng)
    assert (arm, source) == ("small", "linucb")


def test_update_clamp_reward_dans_0_1():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=2, alpha=0.0, epsilon=0.0)
    x = [1.0, 1.0]
    linucb.update("small", x, 99.0)  # anti-windup : clampé à 1.0
    assert linucb.state("small")["b"] == [1.0, 1.0]
    linucb.update("large", x, -3.0)  # clampé à 0.0
    assert linucb.state("large")["b"] == [0.0, 0.0]


def test_reset_si_matrice_singulière():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=2, alpha=0.5, epsilon=0.0, lam=1.0)
    linucb.update("small", [1.0, 0.0], 1.0)
    # on corrompt A (matrice nulle -> singulière) : le prochain choose reset le bras
    state = linucb.state("small")
    state["A"] = [[0.0, 0.0], [0.0, 0.0]]
    rng = random.Random(0)
    linucb.choose([1.0, 0.0], rng)
    fresh = linucb.state("small")
    assert fresh["n"] == 0
    assert fresh["A"] == [[1.0, 0.0], [0.0, 1.0]]  # λ·I
    assert fresh["b"] == [0.0, 0.0]


def test_solve_gauss_jordan_verifie_A_theta_egal_b():
    from investia.llm.linucb import LinUCB, _solve

    linucb = LinUCB(d=3, alpha=0.0, epsilon=0.0)
    x = [1.0, 0.5, -0.2]
    for _ in range(3):
        linucb.update("small", x, 0.8)
    A = linucb.state("small")["A"]
    b = linucb.state("small")["b"]
    theta = _solve(A, b)
    # A·theta == b
    for i in range(3):
        assert sum(A[i][j] * theta[j] for j in range(3)) == pytest.approx(b[i])


def test_to_from_dict_roundtrip():
    from investia.llm.linucb import LinUCB

    linucb = LinUCB(d=3, alpha=0.7, epsilon=0.1, lam=2.0)
    x = [1.0, 0.3, 0.9]
    linucb.update("small", x, 0.6)
    linucb.update("large", x, 0.1)
    clone = LinUCB.from_dict(linucb.to_dict())
    assert clone.alpha == 0.7 and clone.epsilon == 0.1 and clone.lam == 2.0
    assert clone.state("small") == linucb.state("small")
    assert clone.state("large") == linucb.state("large")
    assert clone.choose(x, random.Random(7)) == linucb.choose(x, random.Random(7))


def test_estimate_cost_cents_model_small_moins_cher():
    from investia.llm.linucb import estimate_cost_cents

    models = make_models()
    now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)  # off-peak small
    q = "x" * 400  # ~100 tokens
    cost_small = estimate_cost_cents(q, models.small, "small", now)
    cost_large = estimate_cost_cents(q, models.large, "large", now)
    assert cost_small > 0
    assert cost_small < cost_large / 5  # au moins 5x moins cher hors peak
