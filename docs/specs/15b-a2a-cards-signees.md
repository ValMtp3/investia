# Spec — 15b : Agent Cards A2A signées (JWS, spec v1.0)

*Écrite le : 14/11/2026 | Étape roadmap : 15 (P9 protocoles) | Statut : terminée le 14/11/2026*

## Objectif

Signer les Agent Cards A2A de nos 3 agents (JWS, RFC 8785 canonicalisé — `a2a.utils.signing.create_agent_card_signer`) quand une clé est configurée, et fournir un helper de vérification côté client. a2a-sdk 1.3.0 (dernier, spec v1.0) est déjà installé.

## Pourquoi

Veille 14/11/2026 (brique 9) : la spec A2A v1.0 ajoute les `AgentCardSignature` (JWS) ; 92 % des cards scannées ne sont pas signées → la vérification côté client reste optionnelle. La signature prouve l'intégrité de la card (pas l'identité). Deps : extra `a2a-sdk[signing]` (PyJWT + cryptography) — partie du bump a2a-sdk spec v1.0 validé.

## Contraintes

- `config.py` : `agent_card_signing_key: SecretStr | None = None`, `agent_card_signing_kid: str = "investia-2026"`, `agent_card_signing_alg: str = "ES256"`. Sans clé → cards non signées (rétrocompatible, comportement actuel).
- `cards.py` : `build_agent_card(name, base_url="", signer=None)` — si signer fourni, `card = signer(card)`. `make_card_signer(settings)` (import lazy de `a2a.utils.signing`, PyJWT requis) et `verify_agent_card(card, key, algorithms=["ES256"])` (lazy, lève `NoSignatureError`/`InvalidSignaturesError`).
- `server.py` / `main.py` : le signer est construit une fois si la clé est renseignée et passé à `mount_agents`.
- Zéro régression : sans clé configurée, cards strictement identiques à aujourd'hui ; `test_agents_a2a.py` inchangé et vert.
- Aucun secret loggué ; la clé reste dans `.env` (jamais commité).

## Critères d'acceptation

- [ ] `uv run pytest tests/test_a2a_signing.py -q` passe : card signée avec une clé ES256 générée en test → `card.signatures` non vide ; `verify_agent_card` OK avec la bonne clé, lève `InvalidSignaturesError` avec une mauvaise clé, `NoSignatureError` sur card non signée ; `build_agent_card` sans signer → `signatures == []`.
- [ ] `uv run pytest tests/test_agents_a2a.py -q` passe sans modification.
- [ ] `uv run pytest -q -m "not integration"` passe ; ruff/ty/format propres sur les fichiers touchés.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/src/investia/agents/cards.py` | `signer` param, `make_card_signer`, `verify_agent_card` (imports lazy) |
| `backend/src/investia/agents/server.py` | `mount_agents(..., card_signer=None)` |
| `backend/src/investia/main.py` | construit le signer depuis la config si clé présente |
| `backend/src/investia/config.py` | 3 nouveaux champs optionnels |
| `backend/tests/test_a2a_signing.py` | tests TDD (clé ES256 générée en test) |
| `backend/pyproject.toml` | `a2a-sdk[signing]` (extra, PyJWT + cryptography) |
| `.env.example` | `AGENT_CARD_SIGNING_KEY` commenté |

## Comment vérifier

```bash
cd backend && uv run pytest tests/test_a2a_signing.py tests/test_agents_a2a.py -q
cd backend && uv run pytest -q -m "not integration"
```

## Hors périmètre

Vérification systématique côté orchestrateur (flag `verify_cards`, off par défaut — 92 % des cards externes non signées), découverte dynamique d'agents (well-known déjà en place), registre AGNTCY, 15c (AG-UI).
