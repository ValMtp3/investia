"""Calibration offline du routeur LinUCB (chantier 23d, veille D94).

Rejoue les feedbacks enregistrés (ou un dataset de cas avec `expected_model`)
dans une simulation déterministe de la boucle fermée, sweep une grille
(alpha × epsilon × cost_weight), et écrit le meilleur jeu d'hyperparams dans
`evals/generated/router_calibration.json` (gitignoré). Scorer externe type
RouterArena = lecture manuelle du JSON produit.

Deux modes :
- `--source feedbacks` : rejoue `router_feedback` (replay honnête : on ne met à
  jour le bras choisi que s'il correspond au modèle observé) ;
- `--source cases --cases ...` : rejoue un YAML de cas (mode counterfactual :
  reward = 1.0 si le bras choisi == expected_model, coût estimé).

Usage :
    uv run python -m investia.evals.calibrate_router --source feedbacks
    uv run python -m investia.evals.calibrate_router --source cases \
        --cases evals/generated/cases-live.yaml --seed 42
"""

import argparse
import asyncio
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from investia.llm.linucb import (
    FeatureContext,
    LinUCB,
    build_features,
    estimate_cost_cents,
)
from investia.llm.models import ModelsConfig, load_models_config

GRID_ALPHA = (0.1, 0.3, 1.0)
GRID_EPSILON = (0.0, 0.05, 0.1)
GRID_COST_WEIGHT = (0.0, 0.1, 0.5)
BUDGET_CENTS = 100.0
MIN_MATCHED = 1
DEFAULT_OUT = Path("evals/generated/router_calibration.json")


class FeedbackReader(Protocol):
    async def all_feedbacks(self) -> list[dict[str, Any]]: ...


def _features(
    question: str,
    knn_small: float,
    knn_large: float,
    models: ModelsConfig,
    now: datetime,
) -> list[float]:
    estimate = estimate_cost_cents(question, models.small, "small", now)
    ctx = FeatureContext(
        knn_small=knn_small,
        knn_large=knn_large,
        now=now,
        models=models,
        budget_cents=BUDGET_CENTS,
        cost_estimate_cents=estimate,
    )
    return build_features(question, ctx)


def _simulate(
    events: list[tuple[str, str, bool | None, float]],
    alpha: float,
    epsilon: float,
    cost_weight: float,
    seed: int,
    models: ModelsConfig,
    counterfactual: bool,
    now: datetime,
) -> dict[str, Any]:
    """Rejoue les événements. En replay (feedbacks), on ne met à jour que si le
    bras choisi == le modèle observé. En counterfactual (cas), on met toujours à
    jour avec reward = 1.0 si bras == expected_model."""
    linucb = LinUCB(alpha=alpha, epsilon=epsilon)
    rng = random.Random(seed)
    matched = 0
    sum_reward = 0.0
    sum_success = 0.0
    sum_cost = 0.0
    for question, model, success, cost in events:
        # proxy k-NN hors-ligne : neutre (0.5) — on n'a pas les voisins ici
        x = _features(question, 0.5, 0.5, models, now)
        arm, _source = linucb.choose(x, rng)
        if counterfactual:
            reward = 1.0 if arm == model else 0.0
            cost_cents = estimate_cost_cents(question, models.by_key(arm), arm, now)
            linucb.update(arm, x, reward - cost_weight * cost_cents / BUDGET_CENTS)
            matched += 1
            sum_reward += reward
            sum_success += reward
            sum_cost += cost_cents
        elif arm == model:
            reward = (1.0 if success else 0.0) - (
                cost_weight * min(cost, BUDGET_CENTS) / BUDGET_CENTS
            )
            clamped = min(1.0, max(0.0, reward))
            linucb.update(arm, x, reward)
            matched += 1
            sum_reward += clamped
            sum_success += 1.0 if success else 0.0
            sum_cost += cost
    return {
        "mean_reward": sum_reward / matched if matched else 0.0,
        "success_rate": sum_success / matched if matched else 0.0,
        "mean_cost_cents": sum_cost / matched if matched else 0.0,
        "n": matched,
    }


def _sweep(
    events: list[tuple[str, str, bool | None, float]],
    seed: int,
    min_success: float,
    models: ModelsConfig,
    counterfactual: bool,
    now: datetime,
) -> dict[str, Any]:
    results = []
    for alpha in GRID_ALPHA:
        for epsilon in GRID_EPSILON:
            for cost_weight in GRID_COST_WEIGHT:
                metrics = _simulate(
                    events,
                    alpha,
                    epsilon,
                    cost_weight,
                    seed,
                    models,
                    counterfactual,
                    now,
                )
                results.append(
                    {
                        "alpha": alpha,
                        "epsilon": epsilon,
                        "cost_weight": cost_weight,
                        **metrics,
                    }
                )
    candidates = [
        r for r in results if r["success_rate"] >= min_success and r["n"] >= MIN_MATCHED
    ]
    if candidates:
        best = max(candidates, key=lambda r: (r["mean_reward"], -r["mean_cost_cents"]))
    else:
        best = None
    return {
        "seed": seed,
        "min_success": min_success,
        "grid": {
            "alpha": list(GRID_ALPHA),
            "epsilon": list(GRID_EPSILON),
            "cost_weight": list(GRID_COST_WEIGHT),
        },
        "results": results,
        "best": best,
    }


def _write(out: Path, result: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def calibrate_from_feedbacks(
    store: FeedbackReader,
    out: Path,
    *,
    seed: int = 42,
    min_success: float = 0.8,
    models: ModelsConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mode replay : rejoue les feedbacks réels (router_feedback)."""
    models = models or load_models_config()
    now = now or datetime.now(UTC)
    feedbacks = asyncio.run(store.all_feedbacks())
    events = [
        (fb["question"], fb["model"], fb["success"], fb["cost_cents"])
        for fb in feedbacks
    ]
    result = _sweep(events, seed, min_success, models, counterfactual=False, now=now)
    _write(out, result)
    return result


def calibrate_from_cases(
    cases_path: Path,
    out: Path,
    *,
    seed: int = 42,
    min_success: float = 0.8,
    models: ModelsConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mode counterfactual : rejoue un YAML de cas (expected_model)."""
    from investia.evals.runner import load_cases

    models = models or load_models_config()
    now = now or datetime.now(UTC)
    events = [
        (case.question, case.expected_model, None, 0.0)
        for case in load_cases(cases_path)
        if case.expected_model
    ]
    result = _sweep(events, seed, min_success, models, counterfactual=True, now=now)
    _write(out, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investia.evals.calibrate_router",
        description="Calibration offline du routeur LinUCB (grille alpha x epsilon x "
        "cost_weight) sur les feedbacks ou un dataset de cas",
    )
    parser.add_argument("--source", choices=["feedbacks", "cases"], default="feedbacks")
    parser.add_argument(
        "--cases",
        default="evals/generated/cases-live.yaml",
        help="YAML de cas (mode cases)",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON de sortie")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-success", type=float, default=0.8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    if args.source == "cases":
        result = calibrate_from_cases(
            Path(args.cases), out, seed=args.seed, min_success=args.min_success
        )
    else:

        async def _run() -> dict[str, Any]:
            from investia.db import get_session
            from investia.llm.router_store import DbLinUCBStore

            store = DbLinUCBStore(get_session())
            feedbacks = await store.all_feedbacks()
            events = [
                (fb["question"], fb["model"], fb["success"], fb["cost_cents"])
                for fb in feedbacks
            ]
            models = load_models_config()
            result = _sweep(
                events,
                args.seed,
                args.min_success,
                models,
                counterfactual=False,
                now=datetime.now(UTC),
            )
            _write(out, result)
            return result

        result = asyncio.run(_run())
    best = result["best"]
    if best is None:
        print(f"aucune config n'atteint min_success={result['min_success']} -> {out}")
        return 1
    print(
        f"best: alpha={best['alpha']} epsilon={best['epsilon']} "
        f"cost_weight={best['cost_weight']} "
        f"(mean_reward={best['mean_reward']:.3f}, "
        f"success_rate={best['success_rate']:.3f}, n={best['n']}) -> {out}"
    )
    print(
        "à appliquer via ROUTER_LINUCB_ALPHA / ROUTER_LINUCB_EPSILON "
        "/ ROUTER_LINUCB_COST_WEIGHT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
