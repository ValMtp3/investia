# Spec — 17d : compaction « working set » non destructive + hook PreCompact bloquant

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026*

## Objectif

Renforcer la compaction 16c (sliding window + résumé « NON FIABLE ») avec deux patterns vus dans la veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §3.2 et §4.4, source : crush PR #4059 + hooks, codex-cli, opencode) :

1. **Working set verbatim** : ce qu'on jette ne disparaît pas totalement — on préserve **tels quels** (a) tous les messages `role=user` (codex les garde verbatim), (b) les sorties d'outils **en erreur** (chemins/symboles/erreurs exacts, tronquées à 400 car, max 5) — injectés dans un message system séparé marqué « verbatim » (fiable), distinct du résumé marqué « NON FIABLE ».
2. **« Stamp, don't delete »** (opencode `compacted=<ts>`) : le message de résumé porte un horodatage ISO 8601 (`compacté le <ts>`), et la meta de compaction gagne `compacted_at`.
3. **Hook PreCompact bloquant** (crush) : nouveau paramètre optionnel `pre_compact` sur `run_agent` / `_run_once` — callable async `(messages, estimated_tokens, context_max_tokens) -> bool`. S'il renvoie `False`, **aucune compaction ce tour** : on émet l'event `compaction_vetoed` (et on trace un step), puis on continue la boucle normalement. Défaut `None` = autoriser (zéro régression).

## Pourquoi

Un résumé LLM peut perdre un chiffre exact ou une erreur précise qui bloque tout le reste du raisonnement ; garder un « working set » verbatim (questions de l'utilisateur + erreurs exactes) garde le contexte actionnable après compaction. Le hook PreCompact bloquant donne au HITL (validation humaine, étape 15/D57) un point de veto avant que le contexte ne soit modifié — sansModifier l'historique de façon irréversible.

## Contraintes

- Zéro régression : comportement par défaut identique à 16c quand `pre_compact=None` et sans working set nouveau (les tests 16c existants doivent passer sans modification de leur sens).
- Le résumé reste marqué « NON FIABLE » (16c) ; seul le working set verbatim est présenté comme exact.
- Pas de dépendance nouvelle. Pas de câblage HITL du veto dans cette étape (le hook est une capacité,.ex. appelable depuis main.py plus tard).
- Event `compaction_vetoed` = CustomEvent AG-UI générique (aucun changement dans `agui.py`).

## Critères d'acceptation (TDD : tests d'abord)

- [x] `compact_messages` : les messages `user` des blocs supprimés sont conservés verbatim dans le working set ; les sorties d'outils en erreur aussi (tronquées à 400 car, max 5) ; le message working set est distinct du résumé et porte la mention verbatim. Aucun message working set inséré s'il est vide (layout 16c inchangé, test de non-régression).
- [x] Le message de résumé porte `compacté le <ISO8601>` ; meta contient `compacted_at` (None si no-op).
- [x] `run_agent(..., pre_compact=...)` : veto (`False`) → pas de compaction, event `compaction_vetoed` émis + step tracé, `AgentResult.compactions == 0` ; pas de veto → compaction normale. Hook sync ou async accepté. Passé aussi dans la branche consistency_k > 1.
- [x] `uv run pytest -q -m "not integration"` : 581 passed / 1 skip ; ruff / format / ty propres sur les fichiers touchés. `compaction_vetoed` → CustomEvent AG-UI générique (aucun changement `agui.py`).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/compaction.py` | working set verbatim (user + erreurs outils), stamp `compacté le <ts>`, `compacted_at` dans la meta |
| `backend/src/investia/agent/loop.py` | param `pre_compact` sur `run_agent`/`_run_once`, event `compaction_vetoed` + step |
| `backend/tests/test_compaction.py` | nouveaux tests (TDD) |
| `docs/STATUS.md` | étape 17d |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_compaction.py -q
cd backend && uv run pytest -q -m "not integration"
cd backend && uv run ruff check src/investia/agent tests/test_compaction.py && uv run ty check src/investia/agent
```

## Hors périmètre

- Pré-calcul de résumés en arrière-plan (veille) — plus tard.
- Veto HITL hashé câblé sur l'approval registry — capacité livrée ici, câblage plus tard (17e ou chantier sécurité).
- Compaction par nœud event-sourcing (dsh) — non retenu.
