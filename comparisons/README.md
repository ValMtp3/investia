# comparisons/ — Harnais maison vs frameworks 2026 (étape 6.2, D61)

Le même harness (boucle agent + outils + evals) reconstruit avec **LangGraph**, **Pydantic AI** et **OpenAI Agents SDK**, côte à côte avec la version maison, pour comparer via les evals (étape 6.3).

## Pourquoi

D41 : le cœur du harness est écrit à la main pour apprendre. D17 : on mesure ensuite ce que les frameworks apportent (ou pas). Sans comparaison chiffrée, on ne sait pas ce que le maison vaut.

## Organisation

```
comparisons/
├── pyproject.toml        # projet uv autonome (dépend investia via path ../backend)
├── impl/
│   ├── base.py           # interface commune : run_case(...) -> CaseOutcome
│   ├── maison.py         # référence : investia.agent.run_agent + MockLlm
│   ├── langgraph_impl.py # create_react_agent + fake model
│   ├── pydantic_ai_impl.py # Agent + TestModel
│   └── openai_agents_impl.py # Agent + Runner + fake Model
├── tests/test_impls.py   # chaque approche rejoue les cas mock de evals/cases.yaml
├── run_evals.py          # lance les 4 approches -> results.json
└── results.json          # résultats mock (généré)
```

## Lancer

```bash
cd comparisons
uv sync
uv run pytest -q            # les 4 approches passent les cas mock
uv run python run_evals.py  # produit results.json (métriques agrégées)
```

Le mode `--live` (runs LLM réels, budget ~2 €) est prévu pour l'étape 6.3 (D62).

## Dépendances ajoutées (validées, D61)

| Package | Version | Rôle |
|---|---|---|
| langgraph | 1.2.20 | orchestration stateful |
| pydantic-ai | 2.66.0 | agent typé pydantic |
| openai-agents | 0.24.0 | SDK agents officiel OpenAI |

`investia` est référencé en `path = "../backend"` : les 4 approches partagent
les **mêmes outils** (`build_tools`) et les **mêmes cas d'evals**.

## Premiers résultats (mock, 2026-11-07)

Voir `results.json`. Sur 3 cas mock : les 4 approches appellent le bon outil
(tool_ok_rate 1.0). Différences observées : durée moyenne par run
(maison ~2 ms, langgraph ~4 ms, pydantic-ai ~7 ms, openai-agents ~4 ms en
mock — à confirmer en réel en 6.3), et surtout **les garde-fous en code**
(format, langage, disclaimer) ne s'appliquent que dans le harness maison :
les frameworks laissent le modèle répondre librement (métriques à 0 sans
garde-fous). C'est le point principal de la comparaison 6.3.
