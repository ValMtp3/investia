# Spec — 12f : Outils avancés lecture seule (web_search + read_pdf)

*Écrite le : 08/11/2026 | Étape roadmap : 12 (approfondir le harness) | Statut : validée le 08/11/2026 (Brave + Nutrient validés ; sandbox Python = brique 12g séparée)*

## Objectif

Deux nouveaux outils pour l'agent, **lecture seule** : `web_search(query, limit)` (résultats web avec titre/URL/extrait, source Brave Search API) et `read_pdf(url, max_pages)` (texte extrait d'un PDF distant, source Nutrient DWS API). Enregistrés dans `build_tools` uniquement si le service est fourni (rétrocompatible). 2 cas d'evals (`expected_tool`).

## Pourquoi

L'agent ne voit aujourd'hui que les prix et news US. `web_search` lui donne accès à l'actualité générale (sites officiels, communiqués), `read_pdf` aux rapports annuels — deux sources primaires indispensables pour analyser. Lecture seule = zéro risque d'ordre ou d'écriture.

## Contraintes

- Zéro librairie ajoutée : appels HTTP directs (httpx) vers Brave Search API et Nutrient DWS, clés dans `.env` (`BRAVE_API_KEY`, `NUTRIENT_API_KEY`), jamais dans le code. Sans clé → `ToolError` clair (« clé manquante »), jamais de valeur inventée.
- Pattern identique aux outils existants (`BaseTool`, schéma Pydantic, `ToolError`, sortie avec `source` + `timestamp`).
- `build_tools(..., web_searcher=None, pdf_reader=None)` : outils présents seulement si service fourni (rétrocompatible, comme `portfolio_service`).
- Limites : `web_search` limit 1-10 ; `read_pdf` max_pages 1-20, taille PDF max 20 Mo, timeout 30 s. Contenus tronqués (web 500 car./résultat, PDF 20 000 car.) pour tenir dans le contexte.
- Hors périmètre : **sandbox Python (exécution de code) → brique séparée 12g avec revue sécurité dédiée** ; écriture de fichiers, scraping de pages autres que les API.
- Le system prompt cite les nouveaux outils.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_tools_web_search.py tests/test_tools_pdf.py -q` passent (TDD, MockTransport, zéro réseau).
- [ ] `web_search` : sans clé → ToolError « clé manquante » ; avec clé (mock) → résultats avec source/timestamp ; HTTP 429 → ToolError lisible.
- [ ] `read_pdf` : URL non PDF → ToolError ; mock → texte tronqué à 20 000 car. + source/timestamp.
- [ ] `build_tools` : sans les services → 4 outils seulement (rétrocompat, tests existants verts) ; avec → 6 outils.
- [ ] 2 cas dans `evals/cases.yaml` (`web-search`, `read-pdf`) : `tool_used` = 1.0.
- [ ] `uv run python -m investia.evals` (mock) passe avec les nouveaux cas.
- [ ] `uv run ruff check .`, `uv run ty check`, `uv run pytest -q -m "not integration"` verts ; dashboard inchangé (110 tests).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/tools/web_search.py` | création : client Brave + `WebSearchTool` |
| `backend/src/investia/tools/pdf.py` | création : client Nutrient DWS + `ReadPdfTool` |
| `backend/src/investia/tools/__init__.py` | `build_tools(..., web_searcher=None, pdf_reader=None)` |
| `backend/src/investia/agent/prompts.py` | system prompt cite web_search / read_pdf |
| `backend/src/investia/config.py` + `.env.example` | `BRAVE_API_KEY`, `NUTRIENT_API_KEY` (optionnelles) |
| `evals/cases.yaml` | + 2 cas |
| `backend/tests/test_tools_web_search.py`, `test_tools_pdf.py` | tests TDD |

## Comment vérifier

```bash
cd backend
uv run pytest tests/test_tools_web_search.py tests/test_tools_pdf.py -q
uv run pytest -q -m "not integration"
uv run ruff check . && uv run ty check
uv run python -m investia.evals
```

## Hors périmètre

Sandbox Python / exécution de code (brique 12g séparée, revue sécurité), tout outil avec effet de bord, scraping hors API, clés notées dans le code.
