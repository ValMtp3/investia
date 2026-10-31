# 02 — Architecture

## Vue d'ensemble

```text
Navigateur (toi)
   │  HTTPS (investia.valentin-fiess.fr)
   ▼
Nginx Proxy Manager (déjà sur le VPS, gère 80/443 + certificats)
   │  forward-auth ──► Authelia (connexion par session, ~50 Mo)
   │
   ├──► Dashboards (React, SSE + AG-UI pour le chat agent)
   │
   └──► API backend (Python, async)
            ├── Harness (boucle d'agent, outils, garde-fous, mémoire)
            │     ├── Jev (décisions : routage, garde-fous binaires, juge)
            │     ├── GPT-6 Luna (petit modèle, OpenAI)
            │     └── Mistral Large 4 (gros modèle, Mistral — appelé rarement)
            ├── Connecteurs de données ──► API de marché externes
            │            │
            │            ▼
            │         Redis (cache données de marché, TTL)
            ├── Cache sémantique LLM (Redis vector)
            ├── Portefeuille simulé (10 000 € fictifs, ajustable en admin)
            └── Traces (OTel GenAI) et evals
                     │
                     ▼
                PostgreSQL 17 (+ pgvector pour la mémoire sémantique)
```

> **Forward-auth** : avant de laisser passer une requête vers l'app, le Nginx Proxy Manager demande à Authelia « cette personne est-elle bien connectée ? ». Ton app ne gère ni mots de passe ni sessions. Comme un vigile à l'entrée de l'immeuble : une fois passé, personne ne te redemande ton badge à chaque porte. (OIDC, où l'app vérifie elle-même, n'est pas utilisé ici.)

## Les briques

| Brique | Rôle | Langage |
|---|---|---|
| `backend/` | API, harness, connecteurs, portefeuille simulé | Python (uv, Ruff, async) |
| `dashboard/` | Les 4 pages web | TypeScript (React 19 + Vite + TanStack) |
| `evals/` | Jeux de tests de qualité de l'agent (DeepEval, Promptfoo) | Python |
| `deploy/` | Docker Compose + Authelia (NPM déjà présent sur le VPS, hors repo) | YAML |
| PostgreSQL 17 | Portefeuille, mémoire (+ pgvector), traces, evals | — |
| Redis | Cache données de marché (TTL) + cache sémantique LLM | — |

## Principe clé : le code calcule, l'IA interprète

L'IA ne calcule jamais un prix, un rendement ou un indicateur de tête. Elle appelle un **outil** (une fonction Python) qui calcule, puis elle commente le résultat.

Pourquoi : un modèle peut se tromper sur un chiffre avec aplomb. Une fonction Python, non. C'est comme demander à un journaliste de commenter un tableau fourni par un comptable, plutôt que de calculer lui-même.

## Flux d'une question

1. Tu poses une question dans le dashboard.
2. Le backend démarre une **exécution** (un *run*) et ouvre une trace.
3. La boucle d'agent appelle le modèle, qui demande des outils (prix, historique, actualités).
4. Les outils répondent avec des données sourcées.
5. Le modèle rédige une réponse structurée.
6. Les **garde-fous** vérifient la réponse. Refus ou correction si elle ne passe pas.
7. La réponse et la trace sont enregistrées, puis affichées.

## Données principales (PostgreSQL)

| Table (nom provisoire) | Contenu |
|---|---|
| `runs`, `run_steps` | Une exécution et ses étapes (outil, entrée, sortie, coût, durée, spans OTel) |
| `portfolios`, `positions`, `orders`, `capital_adjustments` | Portefeuille fictif (10 000 € de départ), ordres simulés, historique des ajustements de capital faits en mode admin |
| `memories` (+ colonne `embedding` pgvector) | Profil de risque, préférences, faits retenus |
| `eval_runs`, `eval_results` | Scores des évaluations dans le temps |

> Le cache des données de marché vit dans **Redis** (TTL), pas dans PostgreSQL.

## Stack validée (✅ 30/10/2026 — P1, P2, D29, D30 — détail dans `11-stack-moderne-2026.md`)

| Besoin | Choix | Pourquoi |
|---|---|---|
| API Python | **FastAPI** (async) + Granian/Uvicorn | Écosystème le plus large, Pydantic v2 intégré |
| Accès base | **SQLAlchemy 2.0 async** + Alembic | Standard, migrations versionnées, cohérent avec l'async |
| Appels HTTP | **httpx** (async) | Moderne, gère l'asynchrone |
| Calcul financier | **Polars** + **DuckDB** | Séries de prix rapides (Rust) + backtests SQL embarqués |
| Gestion de projet Python | **uv** + `pyproject.toml` | Toolchain 2026, installs en < 1 min |
| Lint / format / types | **Ruff** + **ty** | Un seul outil Rust pour tout, standard 2026 |
| Tests Python | **pytest** + pytest-asyncio | Standard |
| Gateway LLM | **LiteLLM** (self-hosté, version Docker épinglée) | Une seule API pour OpenAI + Mistral, cost tracking, budgets (Jev : accès direct pour l'instant, Q10) |
| Dashboards | **React 19 + Vite + TanStack Router + TanStack Query + Zustand** | Stack TS moderne, type-safe de bout en bout |
| Chat agent dans le dashboard | **AG-UI / CopilotKit** (SSE) | Stream natif agent→frontend, human-in-the-loop |
| Graphiques | **lightweight-charts** (TradingView) | Fait pour les cours financiers |
| Cache | **Redis** (marché + sémantique LLM) | TTL natif, recherche vectorielle intégrée |
| Mémoire sémantique | **pgvector** (extension PostgreSQL) | Suffisant à notre échelle, zéro conteneur en plus |
| Traces LLM | **OpenTelemetry GenAI** (`gen_ai.*`) | Standard 2026, export vers base d'abord |
| Evals | **DeepEval** + **Promptfoo** | pytest-style + red teaming |
| CI/CD | **GitHub Actions** (uv + ruff + pytest + coverage) | À chaque push |

Avant d'installer quoi que ce soit : vérifier les versions à jour. Tout ajout futur est validé avec toi.
