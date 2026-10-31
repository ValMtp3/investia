# Gouvernance des documents

> Mis en place le 31/10/2026. Ce fichier dit **quel document joue quel rôle**. Il ne duplique rien : chaque fait a un seul propriétaire, les autres documents pointent vers lui.

## Pourquoi

Un projet long meurt d'abord par sa documentation : le README décrit un vieux pipeline, les notes d'architecture décrivent une refactor qui n'a jamais eu lieu, et chaque session ré-invente le contexte. Ici, quatre rôles, quatre propriétaires, zéro copie.

## Les quatre rôles

| Rôle | Un seul job | Document propriétaire |
|---|---|---|
| **Constitution** | Les règles que tout agent et tout contributeur doit obéir | `AGENTS.md` (racine) + `docs/06-securite-et-legal.md` |
| **Map** | Ce qui existe, où ça vit, où chercher quoi | `README.md` + `docs/02-architecture.md` + `docs/10-glossaire.md` + `docs/08-roadmap.md` |
| **Status** | Où on en est maintenant : étape en cours, bloqueurs, suppressions intentionnelles | `docs/STATUS.md` |
| **History** | Pourquoi on a décidé ça, décisions durables (ADR) | `docs/09-decisions.md` |

## Règles

1. **Un propriétaire par fait.** Les autres documents pointent vers le propriétaire, ils ne copient pas.
2. **On met à jour uniquement le rôle concerné** par un changement :
   - structure ou navigation → la map (`README.md`, `02`, `10`)
   - bloqueur, étape en cours, suppression intentionnelle → `docs/STATUS.md`
   - décision durable et son pourquoi → `docs/09-decisions.md` (ADR)
   - règle de conduite → `AGENTS.md`
3. **Les docs sont des preuves, pas des ordres.** On ne suit pas aveuglément ce qu'un document dit : on vérifie contre le code, les tests et Git. Si un doc contredit le code, on note l'écart au lieu de choisir en silence.
4. **Aucun secret dans les docs** (clés, tokens, données perso) — même dans l'historique.
5. **Zone de suppression** dans `docs/STATUS.md` : ce qui a été retiré volontairement et pourquoi, pour ne pas le recréer par erreur.

## Ordre de lecture en début de session

`AGENTS.md` → ce fichier → `docs/STATUS.md` → la spec de la fonctionnalité en cours (`docs/specs/`).
