# Spec — 5.2 : Serveur MCP exposant les outils Investia

*Écrite le : 2026-11-07 | Étape roadmap : 5.2 | Statut : brouillon (à valider)*

## Objectif

Le backend expose les outils Investia (`get_quote`, `get_history`, `get_indicators`, `get_news`, `get_portfolio`, `simulate_order`) comme **serveur MCP** (Model Context Protocol), joignable en **Streamable HTTP** sur `/mcp` derrière Authelia. N'importe quel client MCP (Claude Desktop, un autre agent) peut alors les appeler (D58).

## Pourquoi

Roadmap étape 5 : « serveur ou client MCP ». `docs/03-harness.md` §9 : MCP = « brancher des outils à l'agent (prise universelle) ». Décision D58 (2026-11-07) : **serveur** MCP via **FastMCP**, transport **Streamable HTTP derrière Authelia**, **tous les outils** exposés y compris `simulate_order` (la validation humaine D57 reste côté harness ; un client MCP externe exécute `simulate_order` directement — ordre toujours **simulé**, jamais réel).

## Contraintes

- **Une dépendance ajoutée, avec accord du propriétaire** : `fastmcp` (SDK MCP officiel Python, maintenu), version épinglée dans `pyproject.toml` via `uv add fastmcp==<version>`.
- Module `backend/src/investia/mcp_server.py` : construit un serveur FastMCP à partir des outils existants (`build_tools(market, portfolio_service=...)`) — chaque outil MCP = un wrapper qui valide l'entrée (schéma Pydantic existant) et renvoie le dict JSON de l'outil, avec `source` + horodatage (déjà le cas).
- `simulate_order` en MCP exécute directement `portfolio_service.place_order` (ordre simulé, en base, jamais réel) — la validation humaine D57 ne s'applique qu'à la boucle `/agent/run`.
- Montage dans FastAPI : le handler Streamable HTTP de FastMCP est monté sur le backend à la route `/mcp` (mount ou route déléguée). Le nginx du dashboard aiguille déjà `/api/` vers le backend : on ajoute `location /mcp/` → backend (SSE/streaming sans buffering, comme `/api/`). Ainsi `/mcp` est derrière Authelia + `EDGE_SECRET` comme tout le reste (D53/D54) : **zéro surface réseau nouvelle**.
- Zéro secret exposé par le MCP : les erreurs d'outils renvoient des messages génériques côté client MCP (le détail reste dans les logs serveur), comme pour les traces (revue sécurité 05/11/2026).
- Ne pas casser : le backend existant, `/agent/run`, la CLI, les evals, les tests. Le serveur MCP partage les mêmes services (market, portfolio) construits au démarrage.
- Le endpoint `/mcp` répond 404/405 proprement hors session Authelia (c'est NPM qui redirige avant ; test local : sans proxy, le backend répond quand même — la protection est au niveau proxy, comme le reste de l'API).

## Critères d'acceptation

- [ ] `uv add fastmcp==<version épinglée>` ; `uv.lock` à jour ; `pyproject.toml` documente la version et le pourquoi (D58).
- [ ] `backend/src/investia/mcp_server.py` : `build_mcp_server(market, portfolio_service)` renvoie un serveur FastMCP avec les 6 outils enregistrés (noms identiques aux outils internes).
- [ ] Chaque outil MCP : entrée validée par le schéma Pydantic de l'outil interne ; sortie = JSON de `tool.run()` (source + horodatage présents) ; `ToolError` → erreur MCP lisible sans détail interne.
- [ ] Montage : `create_app(...)` monte le handler Streamable HTTP sur `/mcp` ; `GET /mcp` (sans session MCP) renvoie une réponse MCP valide (initialize) ou 406 selon le transport — préciser dans le test. `POST /mcp` avec un `initialize` + `tools/list` renvoie la liste des 6 outils avec leurs schémas JSON.
- [ ] `POST /mcp` `tools/call` `get_quote` {symbol: "AAPL"} → prix + source + horodatage (test avec faux market). `tools/call` `simulate_order` → ordre en base (faux portfolio_service) ; `get_portfolio` → portefeuille complet.
- [ ] Schémas exposés = `args_schema.model_json_schema()` des outils existants (pas de doublon de schéma).
- [ ] `dashboard/nginx.conf` : `location /mcp/` aiguillé vers `investia-backend:8000/mcp/` avec `proxy_buffering off` (streaming) — test `test_nginx_conf.py` mis à jour.
- [ ] `cd backend && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check` passent (nouveau `test_mcp_server.py` : build, tools/list, tools/call quote/portfolio/simulate_order, erreur outil → message générique).
- [ ] Test d'intégration local : client MCP (ou simple POST `initialize` + `tools/call`) contre le backend lancé sur la base scratch → `tools/list` renvoie 6 outils, `get_quote` AAPL répond.
- [ ] Docs : `docs/11-stack-moderne-2026.md` (ligne MCP mise à jour), `docs/STATUS.md`, `docs/08-roadmap.md` cochée, `docs/07-deploiement-vps.md` (note : `/mcp` passe par le même proxy host, rien à ouvrir de plus).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/pyproject.toml` / `uv.lock` | ajout de `fastmcp` (version épinglée) |
| `backend/src/investia/mcp_server.py` | création : `build_mcp_server(market, portfolio_service)` + montage Streamable HTTP |
| `backend/src/investia/main.py` | `create_app` monte le serveur MCP sur `/mcp` |
| `backend/src/investia/tools/__init__.py` | (si besoin) exposition des outils sous forme réutilisable par le MCP |
| `backend/tests/test_mcp_server.py` | création : tools/list, tools/call, erreurs, schémas |
| `dashboard/nginx.conf` | `location /mcp/` → backend, streaming |
| `backend/tests/test_nginx_conf.py` | test du nouveau location |
| `docs/11-stack-moderne-2026.md`, `docs/STATUS.md`, `docs/08-roadmap.md`, `docs/07-deploiement-vps.md` | mises à jour |

## Comment vérifier

```bash
cd backend && uv sync && uv run pytest -q -m "not integration" && uv run ruff check . && uv run ruff format --check . && uv run ty check
# live : lancer le backend (base scratch), puis :
curl -X POST http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
# puis tools/list et tools/call get_quote
cd dashboard && npx vitest run && npm run build
```

## Hors périmètre

- Pas de client MCP dans le harness (un client brancherait des outils externes — étape ultérieure éventuelle).
- Pas d'authentification MCP spécifique (la session Authelia + EDGE_SECRET suffit, D53/D58).
- Pas de A2A (c'est l'étape 6).
- Pas de ressources/prompts MCP : seulement des outils (`tools/`).
