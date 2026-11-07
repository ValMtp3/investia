# 11 — Stack moderne 2026 (référence)

> Relevé le **30 octobre 2026** via recherche web. Les versions et prix changent vite : revérifier avant chaque étape. Tout ajout est validé avec toi avant installation.

## Pourquoi cette stack

Tu veux tester ce qui est moderne en 2026 autour des agents et harness IA, pas un vieux projet. Cette page est la référence : chaque outil, son rôle, son état en octobre 2026.

## Cœur IA / harness

| Outil | Rôle | État oct. 2026 | Coût |
|---|---|---|---|
| **Jev** (TypeSafe AI) | Modèle de décision « System One » : état JSON + questions typées → probabilités calibrées + confiance. Pas un LLM, ne rédige pas | Sorti de stealth 15/09/2026, $40M seed. Dispo via API TypeSafe ou OpenRouter (`~typesafe/jev-latest`, endpoint `/api/alpha/decisions`). 21 modèles de décision de 13 makers sur OpenRouter | $0.042/M tokens input, **output gratuit** |
| **LLM-as-Jev** (papier HF 2610.02076) | Variante maison : lire les logprobs d'un LLM sur des choix numériques pour obtenir des décisions calibrées | Recherche 2026 | Coût du LLM |
| **GPT-6 Luna** (OpenAI) | ✅ **Petit modèle retenu** | Fenêtre 1,05M tokens | **$0.10 input / $0.50 output** par M tokens (cached $0.01, batch -50 %) |
| **Mistral Large 4** | ✅ **Gros modèle retenu** (Mistral, fournisseur européen) | MoE ~1,05T params, vision, fenêtre large. Appelé rarement | **$1.36 input / $4.18 output** par M tokens (cached $0.14, batch -50 %) |
| Mistral Small 4 | Alternative petit modèle européen | — | $0.10/$0.30 par M tokens |
| GPT-6.1 Terra | Alternative petit modèle | Sorti 26/10/2026, fenêtre 1,05M tokens | $1 / $5 par M tokens, cached $0.05 |
| GPT-5.6 Sol | Alternative gros modèle OpenAI | — | $5 / $30 par M tokens |
| GPT-6 Astra | Flagship OpenAI | 03/09/2026 | $10 / $50 par M tokens — hors budget, à éviter |
| **LiteLLM** (proxy) | Gateway multi-provider self-hosté (OpenAI + Mistral + ...) derrière une seule API compatible OpenAI, avec budget controls et cost tracking (✅ retenu, D29). Les budgets demandent sa propre base PostgreSQL et une master key. ⚠️ Jev n'est pas un modèle de chat : à tester en accès direct (Q10) | 100+ providers, gratuit en self-host. ⚠️ Incident supply chain mars 2026 : pinner la version Docker | Gratuit (self-host) |
| Prompt caching | Cache automatique des tokens répétés (prompts ≥ 1024 tokens, statique au début) | Natif OpenAI, -90 % sur le répété (10 % du prix) | Économie |
| **Semantic cache** | Réponse cachée pour une question sémantiquement proche (Redis vector ou GPTCache) | Hit rate 25-40 % sur trafic agent | Économie 25-40 % des appels |
| Batch API | Traitement différé des evals | Sortie à -50 % | Économie |

## Protocoles agent (Linux Foundation / AAIF, 2026)

| Protocole | Couche | État oct. 2026 | Usage dans le projet |
|---|---|---|---|
| **MCP** | agent → outils | Spec **2026-07-28** : sessions/handshake supprimés (scale horizontal), MRTR (SEP-2322), lifecycle de dépréciation (SEP-2596). SDK TS sur Web Standards (Bun/Deno/Workers) | ✅ **Étape 5.2 faite le 07/11/2026** : serveur MCP **FastMCP 4.1.6** (Python, officiel) monté dans FastAPI sur `/mcp` (streamable HTTP, D58), 6 outils exposés (quote/history/indicators/news/portfolio/simulate_order) |
| **A2A** | agent → agent | **v1.0 stable** mars 2026, 22k★, 150+ orgs, dans l'Agentic AI Foundation. Extensions x402 (paiements), AP2 (commerce) | ✅ **Étape 6.1 faite le 07/11/2026** : `a2a-sdk` 1.3.0, 3 agents (analyste/risque/rédacteur) exposés en JSON-RPC sur `/api/agents/<nom>` dans le backend, orchestrateur A2A (D60) |
| **AG-UI** (CopilotKit) | agent → frontend | 14.2k★, ~17 event types, transport SSE, STATE_DELTA, interrupts human-in-the-loop. Intégré Microsoft Agent Framework, Google ADK, AWS Strands, Bedrock AgentCore | Étape 4 : chat du dashboard en streaming |
| **A2UI** | generative UI | 1.0, catalogs/surfaces (oct. 2026) | À explorer, optionnel |

## Frameworks de comparaison (étape 6)

| Framework | Force (juillet 2026) |
|---|---|
| **LangGraph** | Workflows stateful complexes, contrôle total de chaque étape |
| **Pydantic AI** | Type-safety Python, validation sans orchestration lourde |
| **OpenAI Agents SDK** | Gratuit MIT, tracing auto (dashboard ou OTel), handoffs, guardrails input/output natifs |
| À noter aussi | Claude Agent SDK, Google ADK, Strands (AWS), CrewAI, Mastra + Vercel AI SDK (TypeScript), Microsoft Agent Framework, Agno, Smolagents, DeepAgents |

## Pourquoi ces stacks (alternatives considérées, 30/10/2026)

**Backend — FastAPI retenu, voici pourquoi :**

| Alternative | Verdict | Pourquoi |
|---|---|---|
| **FastAPI** ✅ | Retenu | Écosystème le plus large en 2026 (docs, exemples, aide facile), Pydantic v2 intégré, async natif. Pour un projet d'apprentissage solo, c'est celui qui donne le plus de ressources |
| Litestar | Bon, écarté | Plus rapide et « FastAPI avec plus de structure intégrée » (DTO, CLI), mais communauté plus petite — moins de réponses quand on bloque |
| BlackSheep (Microsoft) | Bon, écarté | Très rapide, mais écosystème encore plus niche |
| Django + Ninja | Trop lourd | Full-stack avec admin auto — inutile ici, le frontend est séparé |
| NestJS (tout en TS) | Écarté | Unifierait la stack, mais D5 = Python pour l'écosystème calcul/data financier |

**Frontend — React 19 + Vite + TanStack retenu, voici pourquoi :**

| Alternative | Verdict | Pourquoi |
|---|---|---|
| **React 19 + Vite + TanStack Router/Query** ✅ | Retenu | Dashboard perso derrière auth, backend Python séparé : pas besoin de SSR ni de server functions → Vite + Router suffisent, plus simple |
| TanStack Start | Bon, inutile ici | Full-stack TS type-safe — utile si on voulait des server functions TS, mais notre backend est en Python |
| Next.js | Overkill | App Router ajoute 15-20 Ko de runtime RSC + complexité SSR, sans bénéfice pour ce cas |
| SvelteKit / Nuxt | Plus légers | Écosystème plus petit, moins de libs finance matures |

**Ajouts pour le calcul financier (✅ validés, D30)** : **Polars** (remplace pandas, écrit en Rust, 10-100x plus rapide sur les séries de prix) et **DuckDB** (SQL analytique embarqué, parfait pour les backtests locaux sur l'historique Stooq).

## Backend Python (toolchain 2026)

| Outil | Rôle |
|---|---|
| **uv** | Package manager + projet (Rust), `uv run` sans venv, workspaces, installs < 1 min. Remplace pip/poetry/venv |
| **Ruff** | Lint + format + import sort en un seul binaire Rust (800+ règles) |
| **ty** | Type checker d'Astral (remplace mypy) — ou pyright |
| **FastAPI** | API async, Pydantic v2 intégré, OpenAPI auto |
| **SQLAlchemy 2.0 async** + **Alembic** | ORM async + migrations versionnées |
| **httpx** | Client HTTP async |
| **Polars** ✅ | Manipulation des séries de prix (remplace pandas, Rust, 10-100x plus rapide) |
| **DuckDB** ✅ | SQL analytique embarqué — backtests locaux sur l'historique Stooq, zéro serveur |
| **pytest** + pytest-asyncio | Tests |
| **Granian** ou Uvicorn | Serveur ASGI |
| Python **3.12+** (3.14 free-threaded en maturation) | 3.10 est EOL en octobre 2026 |

> Note : Astral (uv, Ruff, ty) a été racheté par OpenAI en mars 2026 — les outils restent open source, à surveiller.

## Frontend (2026)

| Outil | Rôle |
|---|---|
| **React 19** + **Vite** | Base UI + bundler |
| **TanStack Router** | Routing type-safe (remplace React Router) |
| **TanStack Query** | Data fetching, cache, re-fetch |
| **TanStack Start** | Option full-stack TS si besoin plus tard (type-safe end-to-end, +léger que Next.js de 15-20 Ko) |
| **AG-UI / CopilotKit** | Chat agent en streaming (SSE) |
| **lightweight-charts** | Graphiques financiers (TradingView) |
| **Tailwind CSS** + **shadcn/ui** | Style + composants accessibles |
| **Zustand** ou **Jotai** | State global léger |
| **TanStack Form** | Formulaires typés |

## Données, cache, mémoire (retenues le 30/10/2026 — D28)

| Outil | Rôle | Limites oct. 2026 |
|---|---|---|
| **Finnhub** (clé gratuite) | ✅ Prix actions/ETF temps réel US, search, market-status, profils, **news** (`company-news`, `news`) | 60 appels/min au total ; candles/financials/forex/crypto = payants |
| **Stooq** | ✅ Historique actions/ETF (CSV), 12 000+ titres globaux | Clé gratuite (CAPTCHA) depuis 2026, quota journalier. Secours : Massive (ex-Polygon) Basic $0, EOD, 5/min |
| **CoinGecko Demo** | ✅ Crypto : prix, historique, news, Fear & Greed | 100/min, 10 000 crédits/mois, clé demo gratuite, attribution requise |
| **Binance public** | ✅ Secours crypto temps réel, **sans clé** | `data-api.binance.vision`, 1 200 weight/min ; usage perso OK |
| **Frankfurter v2** (ECB) | ✅ Taux de change EUR/USD officiels BCE, sans clé | Taux journaliers |
| **Redis 8** | Cache marché (TTL) + cache sémantique LLM (vector). Recherche vectorielle incluse dans Redis 8 : à confirmer, sinon Redis Stack | Conteneur dédié, même image en local, CI et prod |
| **PostgreSQL 17 + pgvector** | Données durables + mémoire sémantique (pgvector 0.8.6 tient ~10k souvenirs) | Un seul serveur, plusieurs bases |
| **OpenTelemetry GenAI** | Traces LLM standardisées (`gen_ai.*` spans) | Export vers PostgreSQL d'abord ; Langfuse self-hosted plus tard |

## Evals & observabilité LLM

| Outil | Rôle |
|---|---|
| **DeepEval** | Evals en Python style pytest (hallucination, relevancy), open source, tourne en CI |
| **Promptfoo** | CLI YAML, red teaming (50+ plugins : injection, PII, jailbreak). Racheté par OpenAI en 2026, reste open source MIT |
| **Langfuse** | Tracing + prompt management + datasets, self-hostable (partie de ClickHouse) |
| **Pydantic Logfire** | Traces IA (OTel) côte à côte avec les métriques applicatives |
| Helicone / Portkey | Gateways LLM (routing, caching, failover, coût multi-provider) |

## Infra & déploiement

| Outil | Rôle |
|---|---|
| **OVH VPS-1 2026** | 4 vCores, 8 Go RAM, 75 Go — retenu (D21). ⚠️ **Partagé** avec d'autres services existants |
| **Nginx Proxy Manager** | Déjà sur le VPS : gère 80/443, HTTPS, certificats pour `investia.valentin-fiess.fr`. On y ajoute des proxy hosts + forward-auth Authelia. Pas de Caddy en frontal |
| Docker Compose (3 fichiers : base + override local + prod) | `docker compose up` identique en local et en ligne ; aucun port publié en prod (réseau Docker interne seul) |
| **Authelia 4.39** | Auth OIDC légère (~50 Mo), forward-auth (`/api/authz/auth-request`) derrière NPM |
| **GitHub** (public) + **GitHub Actions** | Dépôt + CI (uv, ruff, pytest, coverage) |
| **Uptime Kuma** | Monitoring simple « le service répond-il ? » (si pas déjà un outil de monitoring sur le VPS) |
| Sauvegardes PostgreSQL + test de restauration | Régulier |

## Budget indicatif (solo, oct. 2026)

| Poste | Estimation mensuelle |
|---|---|
| Jev (décisions : routage, garde-fous, juge) | ~0,01-0,10 € (output gratuit) |
| GPT-6 Luna (petit) + semantic cache -30 % | ~2-4 € |
| Mistral Large 4 (gros), appels rares + prompt caching | ~3-6 € |
| Evals via Batch API (-50 %) | ~1-2 € |
| **Total** | **~6-12 €/mois** — dans la cible des 10-20 € |
