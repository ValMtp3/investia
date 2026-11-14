# Spec — 13a : redaction PII/secrets avant stockage des traces

*Écrite le : 14/11/2026 | Étape roadmap : 13 (sécurité de la boucle) | Statut : terminée le 14/11/2026*

## Objectif

Aucune PII (e-mail, téléphone, IP) ni aucun secret (clé API, token) ne finit dans `runs` / `run_steps` : la question, chaque payload d'étape et la réponse finale passent par un redactor **avant** l'INSERT en base.

## Pourquoi

Les payloads `run_steps` contiennent les sorties brutes des outils (web_search, read_pdf, erreurs) : un contenu externe peut embarquer une clé API, un e-mail, un numéro (veille OSS du 14/11/2026, `docs/veille-oss-2026-11-14.md` brique 3 : Presidio + gitleaks). Aujourd'hui, seul le sandbox Python masque les secrets de l'env dans *ses* sorties ; rien ne protège la base de traces.

## Contraintes

- Zéro régression : `DbTraceStore` reste rétrocompatible (redactor par défaut actif et déterministe ; injection possible pour les tests).
- Redaction synchrone, stdlib par défaut (valeurs des secrets de l'env + patterns regex : `sk-…`, `ghp_…`, `AKIA…`, `Bearer …`, e-mails). Presidio en renfort **si importable** (import lazy, aucun téléchargement réseau au runtime, aucun crash si absent).
- Performance : redaction < 5 ms pour un payload de 4 Ko.
- Aucun secret en dur dans le code ; `REDACTED = "***REDACTE***"` (constante existante du sandbox, réutilisée).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_redaction.py -q` passe : valeur d'une clé API de l'env masquée, patterns `sk-…` / `AKIA…` / e-mail masqués, texte normal inchangé, dictionnaires/listes imbriqués parcourus en profondeur.
- [ ] `uv run pytest tests/test_tracing.py tests/test_tracing_integration.py -q` passent toujours (rétrocompat du store).
- [ ] Cas concret : un `log_step` dont le payload contient la valeur d'une variable d'env `*_API_KEY` est stocké avec `***REDACTE***` à la place.
- [ ] `uv run ruff check .` et `uv run ty check .` sans erreur (depuis `backend/`).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/redaction.py` | nouveau : protocole `Redactor`, `EnvSecretRedactor` (stdlib), `PresidioRedactor` (lazy), `ChainRedactor` |
| `backend/src/investia/tracing/store.py` | `DbTraceStore` applique le redactor à `question`, `payload`, `answer` |
| `backend/tests/test_redaction.py` | tests unitaires + test d'intégration du store |
| `backend/pyproject.toml` | ajout `presidio-analyzer` / `presidio-anonymizer` (dépendance validée par le propriétaire le 14/11/2026) |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_redaction.py tests/test_tracing.py -q
cd backend && uv run ruff check . && uv run ty check .
```

## Hors périmètre

Redaction des événements SSE envoyés au dashboard en direct, des logs applicatifs, des spans OTel (`tracing/otel.py`), gitleaks en CI (chantier CI à part), et toute la suite du chantier 13 (13b injection, 13c sandbox OS, 13d HITL).
