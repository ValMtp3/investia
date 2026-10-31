# 09 — Décisions (ADR) et questions ouvertes

> **ADR** (Architecture Decision Record) : une fiche courte qui note une décision et son pourquoi, pour s'en souvenir dans six mois.

## Décisions prises (par toi)

| # | Décision | Pourquoi |
|---|---|---|
| D1 | Objectif : apprendre les harness | C'est le but du projet et pour ton travail chez Shaarp |
| D2 | Portefeuille simulé, aucun ordre réel | Évalue la qualité des conseils sans risque ni cadre légal lourd |
| D3 | Actions, ETF et crypto | Voir tous les types de données, dont le marché ouvert 24h/24 |
| D4 | Documentation en Markdown dans `docs/` | Lue directement par Claude Code, versionnable |
| D5 | Python backend, TypeScript dashboards | Meilleur écosystème de calcul en Python, interface web en TypeScript |
| D6 | Harness écrit à la main (précisé ensuite : multi-provider via LiteLLM, voir D11, D26, D29) | Apprendre en profondeur plutôt que d'utiliser un framework |
| D7 | Données gratuites d'abord | Zéro coût pour apprendre |
| D8 | Usage solo, hébergé sur ton VPS | Apprendre le déploiement sans multi-utilisateurs |
| D9 | Tous les concepts à explorer, ordre cœur vers avancé | Voir `08-roadmap.md` |
| D10 | PostgreSQL (un seul serveur, plusieurs bases si besoin) | Robuste, utile pour ton métier. Un seul conteneur PostgreSQL 17, pas deux |
| D11 | Trois niveaux de modèle : **Jev** (décisions) + **GPT-6 Luna** (petit) + **Mistral Large 4** (gros) | Routage + maîtrise des coûts + tester un fournisseur européen (Mistral) pour le gros modèle. Multi-provider OpenAI + Mistral |
| D12 | **Authelia** auto-hébergé pour la connexion (remplace Authentik) | Beaucoup plus léger (~50 Mo vs 1-2 Go), suffisant pour un seul utilisateur, forward-auth derrière NPM |
| D13 | Docker Compose, intégré derrière le **Nginx Proxy Manager** déjà en place sur le VPS | Le VPS n'est pas dédié : NPM gère déjà le 80/443 et le HTTPS, on ajoute juste des proxy hosts |
| D14 | **SSE** (Server-Sent Events) pour le temps réel, pas de polling | Le serveur pousse les données dès qu'il les a, zéro requête inutile côté client |
| D15 | **Redis** pour le cache (données de marché + cache sémantique LLM) | Le cache avec TTL est le job de Redis, pas de PostgreSQL |
| D16 | **Jev** (TypeSafe AI) comme modèle de décision | Tâches binaires/catégorielles (routage, garde-fous, juge) : 20-200x plus rapide, quasi gratuit ($0.042/M input, output gratuit) |
| D17 | Comparaison à l'étape 6 avec **LangGraph, Pydantic AI, OpenAI Agents SDK** | Mesurer ce que le harnais maison gagne ou perd vs les frameworks 2026 |
| D18 | **CI/CD GitHub Actions** dès l'étape 0 (uv + ruff + pytest + coverage) | Même solo, ne pas pousser du code cassé |
| D19 | Stack Python moderne : **uv, Ruff, ty, pyproject.toml, Python 3.12+** | Toolchain 2026 standard, installs en moins d'une minute |
| D20 | SQLAlchemy 2.0 **async** + Alembic | Cohérent avec FastAPI async |
| D21 | VPS : **OVH VPS-1 2026** (4 vCores, 8 Go RAM, 75 Go disque), **partagé** avec d'autres services existants (dont NPM) | Notre stack ajoute ~2-3 Go ; la marge restante dépend des autres services déjà dessus. Stack la plus légère possible (Authelia, pas Authentik) |
| D22 | Budget LLM : **10-20 €/mois max**, optimisation maximale | Prompt caching, semantic cache, Jev pour les décisions, gros modèle rarement appelé, Batch API |
| D23 | Dépôt Git sur **GitHub** (privé) | Standard, CI gratuite |
| D24 | Approche **moderne 2026** : MCP (spec 2026-07-28), A2A, AG-UI, OTel GenAI, pgvector | Voir `11-stack-moderne-2026.md` pour le détail |
| D25 | Nom de domaine : **`investia.valentin-fiess.fr`** | Sous-domaine dédié, HTTPS géré par le NPM existant |
| D26 | Modèles : Jev (décisions) + **GPT-6 Luna** petit ($0.10/$0.50 par M tokens) + **Mistral Large 4** gros ($1.36/$4.18, cached $0.14) | Multi-provider : OpenAI pour le petit, Mistral (fournisseur français/européen) pour le gros. Appels via gateway ou SDK directs |
| D27 | Portefeuille : **10 000 € fictifs**, devise **EUR**, capital **ajustable en mode admin** (ajouter/retirer de l'argent) | Permet de tester des scénarios avec différents montants |
| D28 | Sources de données gratuites retenues : **Finnhub** (prix actions/ETF + news, 60/min), **Stooq** (historique), **CoinGecko Demo + Binance public** (crypto), **Frankfurter v2/ECB** (taux de change) | Vérifiées le 30/10/2026 : les plus fiables en gratuit. Détail dans `04-donnees-de-marche.md` |
| D29 | **LiteLLM** comme gateway multi-provider (OpenAI + Mistral + Jev derrière une seule API, cost tracking, budgets) | Un seul point d'appel pour tous les modèles, suivi des coûts centralisé. Version Docker épinglée (incident supply chain mars 2026) |
| D30 | **Polars** + **DuckDB** pour le calcul financier | Polars (Rust) remplace pandas pour les séries de prix ; DuckDB = SQL analytique embarqué pour les backtests sur l'historique Stooq |
| D31 | Commit des docs sur `main` avant de créer la branche `feat/etape-0-fondations` | Avoir une base propre pour les PR futures |
| D32 | Repo GitHub privé nommé **`investia`** | Court, correspond au nom du projet |
| D33 | Image Redis : **`redis:8`** (pas redis-stack-server) | La recherche vectorielle est dans PostgreSQL (pgvector), pas besoin côté Redis |
| D34 | Découper les étapes 1 et 4 de la roadmap en sous-étapes maintenant | Trop grosses pour un seul plan, on planifie avant de commencer |
| D35 | Règles du portefeuille simulé : **prix du dernier tick connu + frais proportionnels (0,1 %)** | Ordre hors marché exécuté au dernier prix connu. Simple et reproductible |
| D36 | Vérifier la couverture Europe de Finnhub gratuit **maintenant** (avant l'étape 1) | Savoir si on a du temps réel Europe ou juste US avant de coder la couche données |
| D37 | **Jev derrière LiteLLM** si compatible | Un seul point d'appel pour tous les modèles. Si incompatible, appel direct (à tester) |
| D38 | Traces : **OTel GenAI en PostgreSQL** d'abord ; Evals : **DeepEval (pytest) + Promptfoo** (red teaming) | P5 + P6 validées. Langfuse self-hosted plus tard si besoin |
| D39 | Authelia servi sur un **chemin `/auth`** de `investia.valentin-fiess.fr` (pas de sous-domaine dédié) | Tout regroupé sous un seul domaine, géré par NPM |
| D40 | Sauvegardes PostgreSQL : **`pg_dump` quotidien vers stockage objet (S3/Backblaze B2)** | Backup automatisé hors du VPS, rotation à définir à l'étape 4 bis |

## Propositions à valider (rien n'est décidé)

| # | Proposition | À valider quand | Statut |
|---|---|---|---|
| P1 | **Stack backend** : FastAPI + SQLAlchemy 2.0 async + Alembic + httpx + pytest + **uv** + **Ruff** + **ty** + **Polars** + **DuckDB** | Étape 0 | ✅ **Validé le 30/10/2026** |
| P2 | **Stack frontend** : React 19 + Vite + TanStack Router + TanStack Query + AG-UI/CopilotKit + lightweight-charts + Tailwind/shadcn + Zustand | Étape 4 | ✅ **Validé le 30/10/2026** |
| P3 | Sources de données gratuites | Étape 1 | ✅ Résolu : Finnhub + Stooq + CoinGecko/Binance + Frankfurter (D28) |
| P4 | Gateway multi-provider **LiteLLM** | Étape 1 | ✅ Résolu : LiteLLM retenu (D29) |
| P5 | Traces : OpenTelemetry GenAI en base PostgreSQL d'abord, Langfuse self-hosted plus tard si besoin | Étape 2-3 | ✅ **Validé le 31/10/2026** (D38) |
| P6 | Evals : DeepEval (pytest) + Promptfoo (red teaming) | Étape 3 | ✅ **Validé le 31/10/2026** (D38) |

## Questions ouvertes

| # | Question | Impact | Statut |
|---|---|---|---|
| Q1 | Taille du VPS (RAM, CPU) — VPS partagé avec d'autres services | Étape 4 bis | ✅ Résolu : OVH VPS-1, 8 Go RAM partagés, stack légère retenue (D21) |
| Q2 | Nom de domaine pour le HTTPS | Étape 4 bis | ✅ Résolu : `investia.valentin-fiess.fr` (D25) |
| Q3 | Capital fictif de départ et devise | Étape 4 | ✅ Résolu : 10 000 € EUR, ajustable en mode admin (D27) |
| Q4 | Plafond de budget mensuel OpenAI ? | Étape 1 | ✅ Résolu : 10-20 €/mois max (D22) |
| Q5 | Liste initiale des actifs suivis ? | Étape 1 | ✅ Résolu : **pas de liste initiale**, tu ajoutes les actifs un par un dans le dashboard |
| Q6 | Dépôt Git : quel hébergeur, quand l'initialiser ? | Étape 0 | ✅ Résolu : GitHub privé, étape 0 (D23) |
| Q7 | Mémoire longue : pgvector dans PostgreSQL | Étape 3 | ✅ Résolu : pgvector retenu (pgvector 0.8.6 tient ~10k souvenirs sans dégradation à notre échelle) |
| Q8 | Source actions/ETF exacte | Étape 1 | ✅ Résolu : Finnhub (prix+news) + Stooq (historique), vérifié le 30/10/2026 (D28) |
| Q9 | Actions/ETF européens : le gratuit de Finnhub couvre-t-il l'Europe en temps réel ? Comment convertir USD → EUR pour un portefeuille en EUR (Frankfurter = taux journaliers seulement) ? | Étape 1 (données), étape 4 (portefeuille) | 🔄 **À vérifier maintenant** (D36) : tester la couverture Europe de Finnhub avant l'étape 1 |
| Q10 | Jev passe-t-il derrière LiteLLM ? Son API renvoie des probabilités (`/api/alpha/decisions`), pas du chat | Étape 1 | ✅ Résolu : derrière LiteLLM si compatible, sinon appel direct (D37) |
| Q11 | Plan B si l'API Jev est indisponible (service sorti en sept. 2026, endpoint « alpha ») : règles en dur pour le routage, ou variante LLM-as-Jev ? | Étape 1-2 | ✅ Résolu avec Q10 : dépend de la compatibilité LiteLLM (D37) |
| Q12 | Règles du portefeuille simulé : prix d'exécution d'un ordre, frais, fractions d'action, ordres hors marché ouvert, indice de référence | Étape 4 | ✅ Résolu : prix du dernier tick + frais proportionnels 0,1 % (D35) |
| Q13 | Sous-domaine du portail Authelia (ex. `auth.valentin-fiess.fr`, même domaine parent que `investia.`) | Étape 4 bis | ✅ Résolu : chemin `/auth` sur `investia.valentin-fiess.fr` (D39) |
| Q14 | Sauvegardes PostgreSQL : outil, fréquence, destination hors du VPS | Étape 4 bis | ✅ Résolu : `pg_dump` quotidien vers S3/Backblaze B2 (D40) |
| Q15 | Découper les étapes 1 et 4 de la roadmap (trop grosses pour un seul plan) | Avant l'étape 1 | ✅ Résolu : oui, découper maintenant en sous-étapes (D34) |

## Historique

- 2026-10-30 : cadrage, décisions D1 à D14, création de cette documentation.
- Correction pendant le cadrage : l'hébergement Render avait été supposé par erreur, retiré. L'hébergement est ton VPS.
- 2026-10-30 (mise à jour) : challenge des décisions techniques. Authentik → Authelia (D12), ajout Redis (D15), SSE (D14), Jev (D16), comparaison frameworks (D17), CI/CD (D18), stack Python moderne (D19), async (D20), VPS OVH VPS-1 retenu (D21), budget 10-20 € (D22), GitHub (D23), protocoles modernes 2026 (D24). Voir `11-stack-moderne-2026.md`.
- 2026-10-30 (mise à jour 2) : VPS partagé avec NPM existant (D13, D21) — plus de Caddy en frontal, intégration derrière Nginx Proxy Manager. Domaine `investia.valentin-fiess.fr` (D25). Modèles : GPT-6 Luna petit + Mistral Large 4 gros (D26). Portefeuille 10 000 € ajustable en admin (D27). Projet renommé `Harness IA` → `Investia`.
- 2026-10-30 (mise à jour 3) : LiteLLM retenu comme gateway multi-provider (D29). Sources gratuites vérifiées et retenues (D28) : Finnhub, Stooq, CoinGecko Demo + Binance public, Frankfurter/ECB. Pas de liste d'actifs initiale (Q5). pgvector confirmé pour la mémoire longue (Q7). Revue des stacks backend/frontend : FastAPI + React/TanStack confirmés, alternatives notées dans `11-stack-moderne-2026.md`.
- 2026-10-30 (mise à jour 4) : **stack backend (P1) et frontend (P2) validées**. Polars + DuckDB ajoutés pour le calcul financier (D30). Toutes les décisions structurantes sont prises ; prêt pour l'étape 0.
- 2026-10-31 (relecture) : plan de l'étape 0 corrigé (commande compose depuis `deploy/`, `/health` + `/ready`, Alembic seul, une image par service, tests dans `backend/tests/`, ordre de la Task 6). Docs mises à jour (LiteLLM, Authelia = forward-auth et non OIDC, doublons du glossaire). Nouvelles questions ouvertes Q9 à Q15.
- 2026-10-31 (clôture des questions) : toutes les questions ouvertes Q9-Q15 ont reçu une réponse (D31-D40). P5 et P6 validées (D38). Prochaines étapes : vérifier la couverture Europe de Finnhub (D36), puis découper les étapes 1 et 4 en sous-étapes (D34), puis lancer l'étape 0 (commit docs sur `main` puis branche `feat/etape-0-fondations`, repo GitHub `investia`).
