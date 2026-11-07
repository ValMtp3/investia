# Spec — 6.2 : Le même harness reconstruit avec LangGraph, Pydantic AI, OpenAI Agents SDK

*Écrite le : 2026-11-07 | Étape roadmap : 6.2 | Statut : brouillon (à valider)*

## Objectif

Dans un dossier **`comparisons/`** à la racine du repo, reconstruire le **même harness** (boucle agent + outils + garde-fous) avec trois frameworks 2026 — **LangGraph**, **Pydantic AI**, **OpenAI Agents SDK** — pour pouvoir lancer les mêmes evals sur les 4 approches (maison + 3 frameworks) à la 6.3.

## Pourquoi

D17/D41 : le harness cœur est écrit à la main pour apprendre ; on mesure ensuite ce que les frameworks apportent (ou pas). D61 : les implémentations vivent côte à côte dans `comparisons/`. `docs/11-stack-moderne-2026.md` lignes 39-41 pour le pourquoi de chaque framework.

## Contraintes

- **Trois dépendances ajoutées avec accord**, versions épinglées : `langgraph`, `pydantic-ai`, `openai-agents` (via `uv add --group dev` ou groupe dédié `comparisons` pour ne pas alourdir la prod — à décider, mais le groupe dev/comparisons est préférable).
- `comparisons/` isolé : son propre `pyproject.toml` (projet uv séparé) ou dépendances dans un groupe optionnel du backend — **ne pas polluer les dépendances de prod**. Recommandé : `comparisons/` = projet uv autonome avec son propre venv, import du code investia en local (path) pour partager outils/garde-fous/evals.
- Chaque implémentation expose la **même interface** : `run(question: str) -> AgentResult`-like, avec les mêmes outils (`build_tools`), les mêmes garde-fous (`run_all_checks`), le même format de sortie.
- Les 3 implémentations sont testées avec les **mêmes evals mock** que le harness maison (`evals/cases.yaml`, mode mock déterministe) : `comparisons/run_evals.py` lance les 4 approches et produit un tableau JSON.
- Zéro impact sur le backend de prod : aucun import de comparisons/ dans `backend/src` ; la CI ne build pas comparisons/ (ou job séparé optionnel).
- Pas de nouvelle source de données, pas de nouvel outil : on compare l'**orchestration**, pas les données.

## Critères d'acceptation

- [ ] `comparisons/` existe avec `pyproject.toml` (dépendances épinglées : langgraph, pydantic-ai, openai-agents), README expliquant le but.
- [ ] `comparisons/langgraph_impl.py`, `comparisons/pydantic_ai_impl.py`, `comparisons/openai_agents_impl.py` : chacune expose `async def run(question, llm, tools) -> result` avec la même signature que le harness maison.
- [ ] `comparisons/run_evals.py` : lance les 4 approches sur `evals/cases.yaml` (mode mock, LLM fake identique) → `comparisons/results.json` (scores par approche + coût + latence).
- [ ] Tests : chaque impl passe les cas mock d'evals (mêmes assertions que le harness maison) ; `cd comparisons && uv run pytest -q` vert.
- [ ] Le harness maison reste inchangé : `cd backend && uv run pytest -q -m "not integration"` toujours vert.
- [ ] Doc `comparisons/README.md` : comment lancer, quelles métriques, premiers résultats.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `comparisons/pyproject.toml`, `uv.lock` | création, 3 dépendances épinglées |
| `comparisons/langgraph_impl.py` | création |
| `comparisons/pydantic_ai_impl.py` | création |
| `comparisons/openai_agents_impl.py` | création |
| `comparisons/run_evals.py` | création : lance les 4 approches, produit results.json |
| `comparisons/tests/` | tests par implémentation (mêmes evals mock) |
| `comparisons/README.md` | guide + premiers résultats |
| `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/09-decisions.md` | avancement 6.2, D61 (déjà noté) |

## Comment vérifier

```bash
cd comparisons && uv sync && uv run pytest -q && uv run python run_evals.py --mock
# results.json produit : 4 approches x scores/coût/latence
cd backend && uv run pytest -q -m "not integration"   # le prod n'a pas changé
```

## Hors périmètre

- Pas de déploiement des versions framework (pas de conteneur, pas de route API) : la comparaison est locale.
- Pas de MCP/A2A pour les versions framework (la 6.1 couvre le multi-agents du harness maison).
- Pas de Go/Rust ici (c'est P7, à côté dans la 6.3).
- Pas de changement du harness maison.
