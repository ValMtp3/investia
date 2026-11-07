# Spec — 1.4 : Boucle d'agent en CLI

*Écrite le : 2026-10-31 | Étape roadmap : 1.4 | Statut : validée*

## Objectif

`uv run python -m investia.cli "Quel est le prix de AAPL ?"` lance une boucle d'agent qui répond en appelant les outils (étape 1.2) et en citant des chiffres issus de ces outils. C'est le critère de fin de l'étape 1.

## Pourquoi

C'est le cœur du harness (doc 03 §1) : la boucle réfléchir → appeler un outil → lire le résultat → recommencer. Sans elle, pas d'agent. D41 : écrit à la main, zéro framework.

## Contraintes

- Boucle **max N tours** (8 par défaut) et **budget max par run** (réutilise le budget du `LlmClient`, étape 1.3) : dépassement → arrêt propre avec message clair.
- À chaque tour : appel LLM avec `tools=` (les 4 outils en format OpenAI). Si le modèle demande des `tool_calls` : exécuter chaque outil (args validés par Pydantic), résultat ajouté aux `messages` avec `role="tool"`. Sinon : réponse finale.
- **Erreur d'outil** → renvoyée au modèle sous forme lisible (`role="tool"`, contenu = erreur), jamais avalée.
- **System prompt** : analyste financier, règles en dur — citer les sources, jamais de chiffre inventé, mention « simulation, pas un conseil ».
- Le run affiche en console : tours, outils appelés (nom + args), coût total en centimes.
- Routeur (étape 1.3) choisit le modèle pour le premier appel ; les tours suivants gardent le même modèle.
- Tests : `LlmClient` et `MarketService` mockés (MockTransport / fake), zéro réseau. TDD.
- CLI : `cli.py` avec `main(argv)`, testée avec args mockés + un test subprocess `--help`.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_agent_*`).
- [ ] Scénario mocké complet : question → le modèle demande `get_quote(AAPL)` → l'outil renvoie un prix → la réponse finale contient ce prix. Vérifié sur les messages envoyés.
- [ ] Max tours : un modèle qui redemande toujours des outils → arrêt après 8 tours avec un message clair (pas de boucle infinie).
- [ ] Outil en erreur → le message `role="tool"` contient l'erreur lisible, pas de crash.
- [ ] Args invalides envoyés par le modèle → erreur de validation Pydantic renvoyée au modèle.
- [ ] `uv run python -m investia.cli --help` affiche l'aide (test subprocess).
- [ ] Le coût total du run est affiché et ne dépasse pas le budget.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/__init__.py` | création : `run_agent(question, ...)` |
| `backend/src/investia/agent/loop.py` | création : la boucle (tours, tool_calls, exécution, budget) |
| `backend/src/investia/agent/prompts.py` | création : system prompt |
| `backend/src/investia/cli.py` | création : `main(argv)` + point d'entrée `__main__.py` |
| `backend/tests/test_agent_*.py` | création : boucle mockée (scénarios ci-dessus) |

## Comment vérifier

```bash
cd backend && uv run pytest -q
uv run python -m investia.cli --help
# live (vraies clés dans .env) :
uv run python -m investia.cli "prix de AAPL ?"
```

## Hors périmètre

Garde-fous (étape 2), traces en base/OTel (étape 2), Jev (1.5), API/SSE (étape 4), portefeuille (4.x).
