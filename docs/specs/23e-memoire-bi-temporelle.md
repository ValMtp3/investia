# Spec 23e — Mémoire bi-temporelle : supersede auto, scrub secrets, purge RGPD

> Chantier 23e, issu de la veille OSS du 15/11/2026 (`docs/veille-oss-2026-11-15.md`, D94,
> §mémoire). Constats à date (vérifiés dans le code le 15/11) :
> - **16a déjà en place** : colonnes `valid_from` / `valid_until` / `superseded_by` /
>   `provenance` / `scope` (migration 0009), index HNSW partiel sur les souvenirs courants,
>   `save()` avec dédup sémantique à 0,97 (no-op si quasi identique), `supersede()` manuel,
>   `forget()` = soft delete, `recall(include_history=...)`.
> - **Trous restants** (veille) : (1) entre 0,85 et 0,97, `save()` insère un doublon « courant »
>   sans archiver l'ancien — la règle retenue par la veille est **supersede-pas-reject**
>   (bug documenté mcp-memory-service v12.10.0 : la dédup rejette les faits mis à jour) ;
>   (2) aucun scrub des secrets avant écriture mémoire (MemCut, arXiv 2610.21405 : les
>   secrets persistent en mémoire longue — on a `redaction.py` 13a, juste pas branché ici) ;
>   (3) `forget` est soft uniquement — pas de purge hard RGPD (Bemula arXiv 2610.18052 :
>   aucun système testé ne satisfait les demandes d'oubli).

## Objectif

Trois deltas, TDD, zéro régression (comportements 16a inchangés par défaut) :

### 1. Zone intermédiaire « supersede » automatique dans `save()`

- Nouveau seuil `SUPERSEDE_THRESHOLD = 0.85` (param `supersede_threshold` de `save()`,
  défaut 0.85) + fonction pure testable :
  `dedup_action(score, dedup_threshold=0.97, supersede_threshold=0.85) -> "duplicate" | "supersede" | "insert"`.
- `DbMemoryStore.save()` : score ≥ 0,97 → `SaveResult(duplicate=True)` (inchangé) ;
  0,85 ≤ score < 0,97 → archive l'ancien (`valid_until=now()`, `superseded_by=new`) + insert
  le nouveau, `SaveResult(id=new, duplicate=False, superseded=old_id)` ; score < 0,85 →
  insert simple (inchangé). `SaveResult` gagne `superseded: str | None = None`.
- Le protocole `MemoryStoreProtocol.save` gagne le param `supersede_threshold` ; le fake
  de test (`FakeTemporalMemoryStore`) est mis à jour en conséquence.

### 2. Scrub des secrets avant écriture mémoire (MemCut)

- Helper `scrub_content(content, redactor=None) -> tuple[str, bool]` dans `memory/store.py`,
  qui passe le contenu dans `RegexRedactor` (13a, déjà en prod pour les traces) ; retourne
  (texte nettoyé, a_été_modifié).
- Appliqué dans `DbMemoryStore.save()` et `supersede()` **avant** l'embedding et l'INSERT
  (on embedde le texte nettoyé, jamais le secret). `SaveResult` gagne `redacted: bool = False`.
- Test unitaire pur sur `scrub_content` (clé `sk-...` masquée) + test d'intégration pgvector
  marqué `@pytest.mark.integration` (save avec un secret → ligne stockée redacted).

### 3. Purge hard RGPD + audit (mini-Bemula)

- Migration **0011** : table `memory_purge_audit (id UUID PK, memory_id UUID, content_redacted
  TEXT, reason TEXT, purged_at TIMESTAMPTZ DEFAULT now())`.
- Protocole : `purge(memory_id: str, reason: str) -> bool` ; `DbMemoryStore.purge` = DELETE
  hard de la ligne + INSERT dans l'audit (contenu stocké **redacted**). `forget()` reste le
  soft delete (inchangé).
- Outil `forget_memory` : `ForgetMemoryArgs` gagne `hard: bool = False` → `purge` si hard
  (sinon soft, inchangé). Le tool description documente la différence.
- Test « oubli » (style Bemula) : après `purge`, `recall(include_history=True)` et `history()`
  ne retournent plus rien, et une ligne d'audit existe. Test au niveau fake (protocole) +
  test d'intégration pgvector marqué.

## Tests (TDD)

- `test_memory_temporal.py` (suite) : `dedup_action` (3 zones), `SaveResult.superseded`,
  fake store : save en zone intermédiaire → ancien archivé + lié, `scrub_content` masque un
  secret, forget hard via outil → purge appelé.
- `test_memory_integration.py` (marqués integration, hors CI) : save avec secret → stocké
  redacted ; purge → ligne supprimée + audit ; supersede auto en zone intermédiaire.
- Test statique migration : tête alembic unique = 0011 (pattern existant).

## Fichiers touchés

- `backend/src/investia/memory/store.py` (dedup_action, scrub_content, save/supersede, purge, protocol)
- `backend/src/investia/memory/tools.py` (ForgetMemoryArgs.hard)
- `backend/alembic/versions/0011_memory_purge_audit.py` (nouveau)
- `backend/tests/test_memory_temporal.py`, `backend/tests/test_memory_integration.py`
- `docs/STATUS.md`, `docs/09-decisions.md` (D98), cette spec

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres, CI verte ; alembic head = 0011.
- Zone 0,85–0,97 : supersede automatique avec lien `superseded_by` (testé).
- Secret dans un contenu mémoire → jamais stocké ni embeddé en clair (testé).
- `forget_memory(hard=true)` → ligne réellement supprimée + audit (testé).
- `forget` soft et recall courant/historique inchangés (tests 16a verts).

## Hors périmètre

- LongMemEval-S en eval régulière (veille — à programmer séparément avec le dataset 22a).
- `observed_at` séparé de `valid_from` (provenance texte suffit en v1).
- Changement de moteur de graphe (Graphiti) — non retenu (veille).
- Data-binding / A2UI côté mémoire — autre chantier.
