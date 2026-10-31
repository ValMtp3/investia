# Spec — 2.1 : Garde-fous en code sur la réponse de l'agent

*Écrite le : 2026-10-31 | Étape roadmap : 2.1 | Statut : validée*

## Objectif

Avant d'afficher la réponse finale de l'agent, des **garde-fous en code** la vérifient : schéma, chiffres sourcés, langage interdit, avertissement simulation. Une réponse avec un chiffre inventé est bloquée. C'est le critère de fin de l'étape 2 (partie garde-fous).

## Pourquoi

Doc 03 §4 : un prompt se contourne, une vérification Python non. L'agent ne doit jamais afficher de chiffre qui ne vient pas d'un outil, ni de langage de « conseil garanti ». D41 : tout est écrit à la main.

## Contraintes

- Module `guardrails/` avec des fonctions pures `check_*(answer, tool_outputs) -> CheckResult(ok, detail)`.
- Checks :
  1. **Format** : la réponse suit le schéma (thèse, risques, confiance 0-100, sources listées) — parsing tolérant (markdown), un schéma Pydantic pour la version structurée.
  2. **Chiffres** : chaque nombre cité dans la réponse doit apparaître dans au moins une sortie d'outil du run (tolérance arrondi ±0.5 %). Sinon → bloqué.
  3. **Langage interdit** : « gain garanti », « sans risque », « sûr », « garanti » → bloqué.
  4. **Avertissement** : la mention « Simulation — pas un conseil » doit être présente.
- Intégration boucle (loop.py) : après la réponse finale, appliquer les checks. Si échec → renvoyer au modèle avec l'erreur (max 2 corrections), sinon retourner un refus clair.
- Les décisions des garde-fous sont loguées dans le résultat du run (pour les traces, 2.2).
- Tests : chaque check testé unitairement (ok/ko), scénario boucle avec correction, TDD. Zéro réseau.

## Critères d'acceptation

- [ ] `cd backend && uv run pytest -q` passe (tous les tests, y compris `test_guardrails_*`).
- [ ] Réponse citant « 344.63 » alors que les outils n'ont renvoyé que « 100 » → check chiffres KO.
- [ ] Réponse contenant « gain garanti » → KO.
- [ ] Réponse sans la mention simulation → KO.
- [ ] Réponse correcte avec sources → toutes les checks OK.
- [ ] Boucle : réponse avec chiffre inventé → le modèle reçoit l'erreur et peut corriger (test mocké, max 2 corrections puis refus).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/guardrails/__init__.py`, `checks.py` | création : CheckResult + les 4 checks |
| `backend/src/investia/agent/loop.py` | modification : applique les garde-fous, corrections max 2 |
| `backend/tests/test_guardrails.py`, `test_agent_guardrails.py` | création |

## Comment vérifier

```bash
cd backend && uv run pytest -q
```

## Hors périmètre

Traces en base / OTel (2.2/2.3), Jev comme juge (renfort plus tard, jamais à la place du code), API HTTP (étape 4).
