# Investia — conseiller en investissement (portefeuille simulé)

> Ancien nom du projet : « Harness IA ». Le projet vit dans `dev_project/Investia`, en ligne sur `investia.valentin-fiess.fr`.

Projet d'**apprentissage** : construire à la main un *harness* d'agent IA, en prenant le conseil en investissement comme terrain d'entraînement.

> **Harness** = tout ce qui entoure le modèle d'IA : ses outils, sa mémoire, ses règles, ses tests, ses journaux. Le modèle est le moteur, le harness est la voiture autour.

⚠️ **Ce projet ne donne aucun conseil financier réel.** Tout se passe avec de l'argent fictif. Voir [`docs/06-securite-et-legal.md`](docs/06-securite-et-legal.md).

## En une phrase

Un agent (harness écrit à la main, modèles Jev + GPT-6 Luna + Mistral Large 4) qui lit des données de marché quasi temps réel (actions, ETF, crypto), propose des analyses sourcées, gère un portefeuille simulé de 10 000 €, et dont chaque étape est tracée, validée et évaluée. Le tout visible dans des dashboards.

## Les décisions déjà prises

| Sujet | Choix |
|---|---|
| Objectif | Apprendre les harness (pas un produit) |
| Conseil | Portefeuille simulé (papier), aucun ordre réel |
| Actifs | Actions, ETF, crypto |
| Backend | Python moderne (uv, Ruff, async) |
| Dashboards | TypeScript (React 19 + TanStack) |
| IA | Harness écrit à la main + **Jev** (décisions) + **GPT-6 Luna** (petit) + **Mistral Large 4** (gros), derrière le gateway **LiteLLM** |
| Données | Gratuites et fiables (vérifiées 30/10/2026) : **Finnhub** (prix+news), **Stooq** (historique), **CoinGecko Demo + Binance public** (crypto), **Frankfurter/ECB** (taux) — cache **Redis** |
| Base de données | Un seul **PostgreSQL 17** (+ pgvector) |
| Cache | **Redis** (marché + sémantique LLM) |
| Mise en ligne | Ton VPS OVH VPS-1 (4 vCores, 8 Go, **partagé**), Docker Compose derrière le **Nginx Proxy Manager** existant |
| Domaine | `investia.valentin-fiess.fr` |
| Connexion | **Authelia** (auto-hébergé, léger, forward-auth derrière NPM) |
| Temps réel | **SSE** (le serveur pousse) + AG-UI pour le chat agent |
| Portefeuille | 10 000 € fictifs, capital **ajustable en mode admin** |
| Budget LLM | 10-20 €/mois max (prompt caching + semantic cache + Jev) |
| CI/CD | GitHub Actions (uv + ruff + pytest) sur dépôt GitHub privé |
| Comparaison | Étape 6 : LangGraph vs Pydantic AI vs OpenAI Agents SDK |
| Utilisateur | Toi seul |

## Organisation IA du projet

- `AGENTS.md` (racine) : règles lues par tous les agents IA à chaque session (stack, commandes, conventions, règles absolues).
- [docs/GOVERNANCE.md](docs/GOVERNANCE.md) : quel document joue quel rôle (constitution / map / status / history).
- [docs/STATUS.md](docs/STATUS.md) : étape en cours, bloqueurs, suppressions intentionnelles. **À lire en début de session.**
- `docs/specs/` : une spec par fonctionnalité, écrite avant le code.
- `.agents/skills/` : procédures réutilisables par les agents IA, versionnées dans le repo.
- `.claude/commands/` : commandes slash (review, explain-diff).

## Où lire quoi

| Document | Contenu |
|---|---|
| [01 — Vision et périmètre](docs/01-vision-et-perimetre.md) | Pourquoi, objectifs, ce qu'on ne fait pas |
| [02 — Architecture](docs/02-architecture.md) | Les briques et comment elles se parlent |
| [03 — Le harness](docs/03-harness.md) | Boucle d'agent, outils, garde-fous, mémoire, evals, traces |
| [04 — Données de marché](docs/04-donnees-de-marche.md) | Sources, limites, cache |
| [05 — Dashboards](docs/05-dashboards.md) | Les 4 pages |
| [06 — Sécurité et légal](docs/06-securite-et-legal.md) | Secrets, accès, limites légales |
| [07 — Déploiement VPS](docs/07-deploiement-vps.md) | Docker Compose derrière NPM (existant), Authelia |
| [08 — Roadmap](docs/08-roadmap.md) | Les étapes, du cœur vers l'avancé |
| [09 — Décisions (ADR)](docs/09-decisions.md) | Pourquoi chaque choix, et les questions ouvertes |
| [10 — Glossaire](docs/10-glossaire.md) | Les mots techniques expliqués |
| [11 — Stack moderne 2026](docs/11-stack-moderne-2026.md) | Toutes les technos retenues/proposées, à jour d'octobre 2026 |
| [GOVERNANCE](docs/GOVERNANCE.md) | Les 4 rôles des documents (constitution / map / status / history) |
| [STATUS](docs/STATUS.md) | Où on en est maintenant : étape en cours, bloqueurs, zone de suppression |

## Conventions

- Documentation en **français**, code et noms de variables en **anglais**.
- Rien n'est ajouté (librairie, outil) sans validation. Les propositions sont marquées « à valider ».
