# Spec 20b — agent cards A2A enrichies de métriques (P9.1 suite)

> Chantier 20 — suite de 20a. Objectif : les agent cards A2A des 3 agents
> affichent leurs **métriques réelles** (issues des feedbacks 18a), servies
> à la volée, pour qu'un client A2A puisse découvrir quel agent réussit sur
> quoi (découverte d'agents, piste P9).

## Contexte (vérifié en local, 14/11/2026)

- `AgentCard` (a2a-sdk 1.3.0, proto) n'a **pas** de champ `extensions` en v1.0 :
  champs = name, description, interfaces, capabilities, skills, signatures…
  Le canal texte libre le plus visible = `description` (et `skills[].tags`).
- La card est construite **statiquement** au mount (`mount_agents` →
  `build_agent_card` → `create_agent_card_routes(card, ...)`).
- Les métriques existent : table `agent_feedback` (migration 0010, colonne
  `agents TEXT` = JSON array, `success BOOLEAN`), remplie par le routeur 18a.

## Objectif

1. `DbAgentFeedback.stats()` (et le protocole `AgentFeedbackStore`) :
   `dict[agent, {"runs": int, "success_rate": float}]` — un appel SQL groupé
   (`jsonb_array_elements_text(agents::jsonb)`).
2. `build_agent_card(..., stats=None)` : si `stats` est fourni pour l'agent,
   la description est enrichie d'une ligne de métriques, ex. :
   `Métriques (feedbacks) : 12 runs, 92 % de succès.`
   Sans stats → card **strictement identique** à aujourd'hui (zéro régression,
   signature JWS 15b incluse — on signe après enrichissement).
3. Card servie **à la volée** : remplacer `create_agent_card_routes(card)` par
   un handler custom qui reconstruit la card à chaque GET via un
   `stats_provider` (callable async `name -> dict | None`), avec erreur avalée
   (DB down → card sans métriques, jamais d'erreur 500).
4. Câblage `main.py` : provider = `DbAgentFeedback.stats()` quand le routeur
   18a est actif, sinon None.

## Choix tranchés (avec le propriétaire)

- Métriques dans la **description** de la card (lisible par tout client),
  pas un endpoint à côté.
- Card reconstruite **à chaque GET** (métriques vivantes), signée si signer.

## Contrat détaillé

### 1. `AgentFeedbackStore.stats()` (agents/router.py + router_store.py)

```python
async def stats(self) -> dict[str, dict[str, float]]: ...
# {"analyste": {"runs": 12.0, "success_rate": 0.92}, ...}
```

- Protocole : méthode par défaut qui lève `NotImplementedError` ? Non — le
  protocole est structurel ; on ajoute juste la méthode au protocole et à
  `DbAgentFeedback`. Les fakes de tests l'implémentent.
- SQL (router_store) :
  ```sql
  SELECT a.agent AS agent,
         count(*) AS runs,
         count(*) FILTER (WHERE f.success)::float / count(*) AS success_rate
  FROM agent_feedback f,
       jsonb_array_elements_text(f.agents::jsonb) AS a(agent)
  GROUP BY a.agent
  ```
- `FixedPipelineRouter`/fakes : stats facultatif (pas dans le protocole
  AgentRouter, qui ne sert qu'au routage).

### 2. `build_agent_card(name, base_url="", signer=None, stats=None)`

- `stats: dict[str, float] | None` = `{"runs": ..., "success_rate": ...}` pour
  cet agent.
- Enrichissement : `description += f"\n\nMétriques (feedbacks 18a) : {runs:.0f} runs, {success_rate:.0%} de succès."`
  (runs=0 → ligne « aucun feedback pour l'instant » ou omise — à fixer :
  **omise si runs == 0**, card inchangée tant qu'aucun feedback).
- Signature appliquée **après** enrichissement.

### 3. Route card dynamique (agents/server.py)

- `build_agent_subapp(card, executor, card_factory=None)` : si `card_factory`
  (callable `async () -> AgentCard`) est fourni, la route
  `/.well-known/agent-card.json` appelle `card_factory()` à chaque GET ;
  sinon comportement actuel (card statique) — zéro régression tests existants.
- `mount_agents(..., stats_provider=None)` : `stats_provider` =
  `async (name: str) -> dict[str, float] | None`. Si fourni :
  `card_factory = lambda: build_agent_card(name, base_url, signer, await stats_provider(name))`.
  Le handler : `try: stats = await stats_provider(name) except Exception: stats = None`.

### 4. Câblage main.py

Quand `agent_router` est un `LearnedAgentRouter` avec store `DbAgentFeedback` :
`stats_provider = store.stats_for(name)` (petit wrapper async qui filtre sur
l'agent et avale les erreurs → None). Sinon None.

### 5. Tests (TDD)

- `tests/test_agents_cards.py` (nouveau ou existant) :
  1. `build_agent_card` sans stats → description exactement égale à l'actuelle
     (test existant le couvre ; on assert inchangé).
  2. avec stats → description contient « 12 runs, 92 % de succès » ; runs=0 →
     description inchangée.
  3. card signée + stats → signature valide (verify_agent_card passe).
  4. Route GET card avec `card_factory` fake → 200 + métriques présentes ;
     factory qui lève → 200 + card sans métriques (erreur avalée).
  5. `DbAgentFeedback.stats()` : test `@pytest.mark.integration` pgvector
     (pattern test_agents_router.py) + test unitaire du mapping lignes → dict.

## Fichiers touchés

- `backend/src/investia/agents/router.py` : protocole `stats()`.
- `backend/src/investia/agents/router_store.py` : `DbAgentFeedback.stats()` (SQL).
- `backend/src/investia/agents/cards.py` : `build_agent_card(..., stats=None)`.
- `backend/src/investia/agents/server.py` : `card_factory` + `stats_provider`.
- `backend/src/investia/main.py` : câblage du provider.
- `backend/tests/test_agents_cards.py` (ou test_agents_a2a.py) + 1 test integration.
- `docs/STATUS.md`, `docs/09-decisions.md` (D88).

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres.
- GET `/.well-known/agent-card.json` renvoie 200 avec et sans stats.
- Zéro régression : sans provider, card byte-identique à 6.1/15b (test de
  description exacte + test de signature existant).

## Hors périmètre

- Métriques d'evals (12h/18b) dans la card — seulement les feedbacks 18a.
- `capabilities.streaming=True` (ce serait P9.1 streaming, autre chantier).
- Dashboard : affichage des métriques (le dashboard lit déjà la card ? à voir).
