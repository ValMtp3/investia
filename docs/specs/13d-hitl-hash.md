# Spec — 13d : HITL durci — approbation liée au hash exact du payload

*Écrite le : 14/11/2026 | Étape roadmap : 13 (sécurité de la boucle) | Statut : terminée le 14/11/2026*

## Objectif

L'approbation humaine de `simulate_order` est liée au **hash SHA-256 exact des arguments affichés** : si le payload change après le « oui » (attaque « replan-after-yes », documentée par UiPath 2026), l'ordre est refusé. Zéro dépendance.

## Pourquoi

Aujourd'hui `ApprovalRegistry.decide(run_id, decision)` n'est lié qu'au `run_id` : la décision « approved » s'applique à la demande en attente sans vérifier que les arguments exécutés sont exactement ceux présentés à l'humain (veille `docs/veille-oss-2026-11-14.md` brique 4).

## Contraintes

- `payload_hash = sha256(json.dumps({symbol, side, quantity}, sort_keys=True))` (canonical, sans run_id/turn).
- Le hash est émis dans l'event SSE `approval_request` et tracé dans le step `approval_request` + `approval` (audit).
- `ApprovalRegistry.open(run_id, payload_hash=None)` et `decide(run_id, decision, payload_hash=None)` : si un hash est enregistré et que celui fourni diffère → `decide` retourne False (409 côté endpoint), aucune décision enregistrée. Rétrocompatible : sans hash des deux côtés, comportement actuel.
- Côté boucle, après la décision : re-vérification du hash des arguments prêts à être exécutés (défense en profondeur) ; mismatch → « ordre refusé (payload modifié après approbation) — aucun ordre exécuté ».
- `ApprovalBody` gagne `payload_hash: str | None = None` (optionnel, rétrocompatible) ; l'endpoint passe le hash à `decide`.
- Zéro régression : `test_agent_approval.py` et `test_main_approval.py` passent sans modification.

## Critères d'acceptation

- [ ] `uv run pytest tests/test_approval_hash.py -q` passe : hash = sha256 hex 64 chars, stable (mêmes args → même hash, ordre des clés indifférent) ; `decide` avec hash erroné → False et aucune décision enregistrée ; avec le bon hash → True ; sans hash → True (rétrocompat).
- [ ] Boucle : le payload de l'event `approval_request` contient `payload_hash` ; une décision enregistrée avec un hash différent de celui de la requête → l'ordre n'est PAS exécuté et le modèle reçoit le message de refus.
- [ ] Endpoint : `POST /agent/runs/{id}/approval` avec `payload_hash` incohérent → 409.
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty/format propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agent/approval.py` | `open(run_id, payload_hash=None)`, `decide(..., payload_hash=None)` avec vérification |
| `backend/src/investia/agent/loop.py` | `_request_approval` : calcule/émet/trace le hash, re-vérifie avant exécution |
| `backend/src/investia/main.py` | `ApprovalBody.payload_hash` optionnel, passé à `decide` (409 si mismatch) |
| `backend/tests/test_approval_hash.py` | tests TDD |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_approval_hash.py tests/test_agent_approval.py tests/test_main_approval.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

Policy externe Cedar/OPA (décider *si* une approbation est requise selon montant/scope — veille, chantier ultérieur), audit append-only en base, changement du dashboard (le hash reste optionnel côté client), multi-approbations par run.
