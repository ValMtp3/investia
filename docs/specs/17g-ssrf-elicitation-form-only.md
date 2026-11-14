# Spec — 17g : blocage SSRF (read_pdf + redirects) + elicitation MCP form-only

*Écrite le : 14/11/2026 | Étape roadmap : 17 | Statut : validée le 14/11/2026, TERMINÉE le 14/11/2026*

## Objectif

Deux durcissements de la veille 14/11/2026 (`docs/veille-oss-2026-11-14-approfondie.md` §4.8–4.9, source hermes security docs) :

**A. SSRF** : `read_pdf` télécharge une URL fournie au modèle avec `follow_redirects=True` et seule une vérification de scheme — une injection indirecte (13b) peut viser `http://169.254.169.254/` (métadonnées cloud) ou `http://localhost:...`. Nouveau module `guardrails/ssrf.py` + application dans le téléchargement PDF, **redirects compris**.

**B. Elicitation MCP form-only** : MCP 2026-07-28 a deux modes d'elicitation — `form` (schéma JSON, sûr) et `url` (le client ouvre un lien : phishing/SSRF). Notre 15a n'émet que du `form` ; on centralise la construction pour qu'un mode `url` soit **impossible** (raise), pas juste non utilisé.

## Constat préalable (vérifié dans le code)

- Le serveur A2A (`agents/server.py`) n'implémente **pas** `pushConfig`/webhook : aucune surface de callback push à bloquer aujourd'hui. Le guard SSRF reste réutilisable pour toute URL entrante future.

## Changements prévus

1. **Nouveau module `backend/src/investia/guardrails/ssrf.py`** :
   - `class SsrfBlockedError(ValueError)` ;
   - `async def assert_public_http_url(url: str) -> str` : scheme http/https uniquement, pas d'userinfo (credentials), host non vide ; IP littérale → `ipaddress.ip_address(host).is_global` exigé ; sinon résolution DNS (`loop.getaddrinfo`, factorisée dans `_resolve_host` pour les tests) → **toutes** les IP doivent être `is_global` (bloque loopback, RFC1918, link-local 169.254.x, reserved, multicast, ::1…).
   - ⚠️ documenté : DNS rebinding — on vérifie à la résolution, on ne pin pas l'IP au fetch (hors périmètre).
2. **`tools/pdf.py`** : `NutrientPdfReader._download` appelle `await assert_public_http_url(url)` avant le GET ; redirects gérés manuellement (max 3, `follow_redirects=False`) avec re-vérification de chaque en-tête `Location` ; blocage → `ToolError` lisible (« SSRF bloqué »).
3. **`mcp_server.py`** : la construction de `ElicitRequest` est extraite dans `_form_elicitation(message, schema)` qui n'accepte que `mode="form"` (raise `ValueError` sinon) — `simulate_order` l'utilise.

## Pourquoi

Une URL contrôlée par un contenu externe (prompt injecté via un PDF/news) ne doit jamais pouvoir atteindre le réseau interne ou les métadonnées cloud du VPS. Le mode `url` de l'elicitation MCP est un vecteur de phishing côté client ; form-only l'élimine par construction.

## Contraintes

- Zéro régression : URL publique http/https inchangée ; tests pdf existants (MockTransport) doivent passer (le guard ne bloque pas `https://...` publiques — les tests mockent la résolution ou utilisent des URLs publiques).
- Pas de dépendance nouvelle (`ipaddress`, `socket`, `asyncio` stdlib).
- Le blocage SSRF produit une `ToolError` claire pour le modèle, pas une exception brute.

## Critères d'acceptation (TDD : tests d'abord)

- [x] `assert_public_http_url` (nouveau `guardrails/ssrf.py`, `_resolve_host` mockable) : OK URL publique ; rejette schémas non-http, userinfo, `https://` sans hôte, IP littérales privées/loopback/link-local/multicast (`224.0.0.1` — check explicite car `is_global` seul le laisse passer), host résolvant vers IP privée (même mélangée à des publiques).
- [x] `read_pdf` : guard avant le 1er GET (test : aucun GET parti pour `169.254.169.254`) ; redirects manuels max 3 (`follow_redirects=False`), chaque `Location` re-vérifié (public→privé bloqué au 1er saut, public→public OK).
- [x] `_form_elicitation` (mcp_server.py) : émet `mode="form"` ; `mode="url"` → ValueError ; tests 15a existants verts.
- [x] A2A : vérifié, pas de `pushConfig`/webhook côté serveur — rien à bloquer aujourd'hui.
- [x] `uv run pytest -q -m "not integration"` : 616 passed / 1 skip ; ruff / format / ty propres sur les fichiers touchés (3 E501 pré-existants ailleurs non touchés).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/guardrails/ssrf.py` | nouveau : `assert_public_http_url`, `SsrfBlockedError` |
| `backend/src/investia/tools/pdf.py` | guard avant GET + redirects manuels re-vérifiés |
| `backend/src/investia/mcp_server.py` | `_form_elicitation` form-only |
| `backend/tests/test_ssrf.py` (nouveau), `test_tools_pdf.py`, `test_mcp_elicitation.py` | tests TDD |
| `docs/STATUS.md` | étape 17g |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_ssrf.py tests/test_tools_pdf.py tests/test_mcp_elicitation.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

- Pin de l'IP résolue au moment du fetch (anti DNS-rebinding complet) — nécessite un transport httpx custom, piste notée.
- Push A2A (`pushConfig`) : non implémenté côté serveur, rien à bloquer ; à réévaluer si on l'ajoute.
- Rate-limit des téléchargements PDF (autre chantier).
