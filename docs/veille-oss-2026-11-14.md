# Veille OSS consolidée — 14 novembre 2026

Rapport de veille demandé par le propriétaire : comparer notre harness maison aux projets open source du moment (harness d'agents, chatbots, et briques transverses) pour savoir si on a déjà tiré le meilleur de l'OSS, et quoi adopter ensuite.

**Méthode** : 8 sous-agents de recherche lancés en parallèle le 14/11/2026 (harness/frameworks, mémoire & context engineering, evals & observabilité, garde-fous & sécurité, routage & coût, multi-agents & protocoles, sandboxing, frontend UI). Canaux vérifiés ce jour-là : recherche web, API GitHub publique, PyPI JSON, npm registry, Hugging Face Hub, OSV. Limites honnêtes : API GitHub rate-limitée (60 req/h), quelques chiffres de perf issus de blogs éditeurs non re-mesurés. Aucun secret dans ce document. Aucune dépendance ajoutée (règle du projet : validation explicite du propriétaire requise).

## Réponse directe : est-on au niveau ?

Oui sur le cœur. La comparaison interne (étape 6.2/6.3 : maison vs langgraph / pydantic-ai / openai-agents) et cette veille externe confirment qu'en novembre 2026 aucun framework OSS ne domine : chacun a ses CVE, son poids ou son lock-in (CrewAI = 4 CVE RCE 2026, agno = 3 CVE, NeMo Guardrails = 128 dépendances, LangGraph = lock-in LangSmith...). Notre combinaison boucle maison + garde-fous **en code** + HITL + traces Postgres + evals maison reste au niveau ou au-dessus.

Les vrais écarts restants sont des **briques transverses précises**, pas le cœur du harness.

## Shortlist consolidée (classée par domaine)

### 1. Sécurité / sandbox (consensus de 3 agents) — prioritaire
- Notre sandbox subprocess stdlib (étape 12g) bloque les maladresses, pas un code adversarial : contournement du patch `socket` via ctypes/libc, `io_uring`, exfiltration DNS, fork bomb (`RLIMIT_NPROC` est par-UID), lecture `/proc` du parent, noyau partagé (PwnEscape CVE-2026-99999, oct 2026).
- **Adopt** une couche OS sous `run_python` : nsjail (Linux, Apache-2.0) / Seatbelt `sandbox-exec` (macOS) / Anthropic `sandbox-runtime` v0.0.83 (Apache-2.0, bwrap + netns + seccomp-BPF). Tier 2 microVM (E2B self-host `e2b-dev/infra` Apache-2.0, ou microsandbox/libkrun) pour le code marqué dangereux, derrière HITL. Pydantic Monty v1.6.0 (MIT, roue Rust, 3 deps) comme backend « calcul pur » sans FS/réseau.
- Pre-hook statique : Bandit 1.9.4 + règles maison (eval/socket/subprocess). Semgrep = CI uniquement (LGPL depuis 2026).
- **Veille** : NVIDIA OpenShell v0.1.8 (kernel-level + vérification formelle Z3, probablement le standard 2027).

### 2. Injection de prompt indirecte (notre vecteur n°1 : résultats web/PDF)
- OWASP Top 10 LLM 2026 : aucun mécanisme fiable contre l'injection → la défense est **architecturale**.
- **Adopt** un classifieur local qui scanne chaque résultat d'outil avant injection dans le contexte : Horizon-Labs `prompt-injection-guard` v2.2 (ONNX, Apache-2.0, multilingue, F1 macro 0.887). Alternative : Meta Llama Prompt Guard 2 22M (licence Llama custom, à lire).
- **Build** maison : délimitation XML (spotlighting) du contenu externe, séparation des privilèges (retirer `simulate_order`/`run_python` quand le contexte contient du contenu externe non fiable), canary tokens dans le system prompt.

### 3. Redaction PII/secrets avant stockage des traces
- Nos `run_steps` loguent les appels d'outils bruts : vecteur réel de fuite de clés API.
- **Adopt** un wrapper fin : Presidio 2.2.366 (MIT, import lazy, modèles spaCy locaux, réseau bloqué après téléchargement) sur les sorties agent et avant tout INSERT en base ; gitleaks v8.30.1 (binaire Go MIT) en pre-commit/CI. TruffleHog réservé à l'audit historique ponctuel (AGPL + vérification active = appels réseau avec les secrets candidats : jamais en prod).

### 4. HITL durci (ApprovalRegistry)
- On a déjà deny-by-default + timeout = refus (conforme aux recommandations 2026). Il manque : le **hash SHA-256 du payload approuvé re-vérifié juste avant l'exécution** (anti « replan-after-yes », documenté par UiPath 2026), une policy externe default-deny (Cedar v4.14 en sidecar binaire — pas de binding PyPI officiel — ou OPA v1.22.4) pour décider *si* une approbation est requise, et un audit append-only.
- HumanLayer est déprécié ; le pattern LangGraph `interrupt()`/checkpointer est la référence mais le framework est lourd → on reste maison.

### 5. Boucle run_agent : gestion d'erreurs des outils (pattern pydantic-ai 2.68)
- Deux classes d'erreur : `RetryableToolError` (feedback au modèle, budget de retries en ladder outil > run, défaut 1) vs `FatalToolError` (stop immédiat). Timeout par outil avec annulation propagée. Fail-fast en cas de dépassement de la limite de tokens de sortie. **Règle absolue** : jamais réexécuter un appel à effet de bord déjà exécuté (leçons agno #10366, openai-agents #5573) → idempotence de `simulate_order`.
- Registre de hooks (`on_model_request` / `on_tool_call` / `on_stream_event`) pour brancher garde-fous, traces et evals sans coupler la boucle.
- AG-UI 1.0 (MIT, spec stable, SDK PyPI `ag-ui-protocol` 1.0.0 = 1 seule dep pydantic) : adopter le **vocabulaire d'événements** pour notre SSE (transport inchangé).

### 6. Mémoire & contexte
- **Build** sur notre pgvector (inspiré Mem0 ADD/UPDATE/DELETE/NOOP + Graphiti `valid_at`/`invalid_at`) : colonnes `valid_from`/`valid_until`, `superseded_by`, `provenance`, `scope`, `confidence` ; dédup sémantique à l'écriture ; recall hybride BM25 (colonne tsvector + index GIN) + vectoriel + filtre temporel.
- **Adopt** des embeddings locaux derrière notre interface existante : Qwen3-Embedding-0.6B (Apache-2.0, 103 M téléchargements) ou `microsoft/harrier-oss-v1-0.6b` (MIT). Jamais jina-embeddings-v5 (CC BY-NC). Valider sur nos propres requêtes (crise de confiance des benchmarks, juillet 2026).
- Compaction de `run_agent` (inspiré Letta / OpenClaw / LangGraph) : sliding window à ~80 % de la fenêtre, garder les N derniers tours intacts, résumé marqué « untrusted », historique jamais supprimé en base (view ≠ record), *memory flush* avant compaction, préservation des UUID/symboles dans le résumé.
- Hindsight v1.2.1 (MIT, pgvector natif, MCP built-in) = plan B si la dette de notre mémoire maison grossit. MemPalace à ignorer (benchmark LongMemEval contesté par une review académique).

### 7. Routage / coût / cache
- Notre routeur k-NN appris est au niveau de l'état de l'art (famille « routeur binaire/cascade », la plus éprouvée). Il manque : l'**ε-exploration bandit** vers le gros modèle, la **calibration du seuil** contre un budget de coût (RouterArena, ICLR 2026), et des features de complexité riches (tokens, présence d'outils, confiance du petit modèle). RouteLLM = baseline d'eval uniquement (figé depuis 08/2024). Weave Router exclu (Elastic License v2). Martian / Not Diamond = SaaS, fuite de prompts.
- LiteLLM proxy (déjà notre gateway) en config YAML zéro code : cache exact Redis, spend tracking Postgres, budgets hiérarchiques, fallbacks + cooldowns, prompt caching (`cache_control`), `/v1/batches` pour les evals offline (−50 %). **Sécurité** : épingler ≥ v1.109.1 (backdoor v1.82.7/v1.82.8, CVE-2026-33634 au CISA KEV ; CVE-2026-30623 RCE via MCP stdio corrigée ≥ v1.83.7).
- `DbSemanticCache` pgvector : ajouter le scoping tenant dans la clé de cache, TTL + éviction LRU, skip si la conversation dépasse N messages, seuil adaptatif par entrée (vCache, ICLR 2026). Bifrost (Go, Apache-2.0, plugin semanticcache avec `conversation_history_threshold=3`) = alternative de gateway si on quitte LiteLLM un jour.

### 8. Evals & observabilité
- **Adopt** DeepEval v4.2.4 (Apache-2.0, style pytest, 100 % local, `ToolCorrectnessMetric`) **en complément — jamais en remplacement** de nos métriques en code (un juge LLM seul n'est pas fiable : biais de position/verbosité, arXiv 2606.19544).
- **Build** un dataset vivant : export read-only des runs tagués « échec » depuis Postgres → dataset versionné (JSONL + hash) rejoué par notre runner maison à chaque changement (zéro dépendance nouvelle, c'est notre avantage « maison »).
- **Adopt** Phoenix v21.1.0 (mono-process + Postgres, ingère l'OTLP que nous émettons déjà → waterfall, datasets depuis les traces, annotations humaines) comme viewer au-dessus de nos spans. Licence Elastic 2.0 : usage interne OK, à valider juridiquement. Langfuse v4 (racheté par ClickHouse) et Opik = self-host lourd (ClickHouse obligatoire).
- Red team : promptfoo (déjà chez nous, racheté par OpenAI le 09/03/2026, licence MIT inchangée à ce jour) + **sondes maison finance** (injection via PDF, exfiltration de secrets, hallucination chiffrée, manipulation d'ordres) ; garak v0.17.1 (NVIDIA, Apache-2.0) en audit trimestriel en CI isolée (~45 deps lourdes, jamais en prod). PyRIT archivé (03/2026) et AgentOps abandonné → ne pas adopter.
- OTel GenAI : épingler `opentelemetry-semantic-conventions` + `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` (conventions encore en `development` ; le dépôt a migré vers `semantic-conventions-genai` sans releases taguées en nov 2026).

### 9. Multi-agents & protocoles (piste P9)
- **MCP spec 2026-07-28** : migrer notre serveur FastMCP (bump `mcp>=2.3` / `fastmcp>=4.2`) ; l'elicitation MRTR en mode formulaire convient exactement à notre HITL `simulate_order` ; sampling/roots sont dépréciés (retrait au plus tôt le 28/07/2027) → ne plus rien bâtir dessus. MCP Registry self-hosté (docker + Postgres) pour cataloguer nos serveurs. `mcp-scan` en mode local uniquement en CI sur notre serveur FastMCP.
- **A2A v1.0** (gouvernance AAIF) : nous avons déjà a2a-sdk 1.3.0 → monter à la spec 1.0, Agent Cards signées (JWS, extra `[signing]`), discovery `/.well-known/agent-card.json`. 92 % des agents ne signent pas leur card → vérification optionnelle côté client.
- **AG-UI 1.0** : émettre nos événements SSE dans ce vocabulaire (`subagentRunId` pour tracer quel agent A2A parle, `interrupt`/resume HITL standardisé).
- Orchestration dynamique : routeur LLM « handoff-as-tool » (inspiré langgraph-swarm / openai-agents, sans les adopter) remplaçant la chaîne en dur analyste→risque→rédacteur, avec fallback = chaîne fixe. Agent Skills (SKILL.md, agentskills.io) pour décrire les skills de nos agents. AGNTCY `dir` = veille (jeune, draft IETF).

### 10. Frontend dashboard
- **Adopt** streamdown 2.7.1 (Apache-2.0, 154 Ko gzip, 11 M dl/sem) pour remplacer notre renderer markdown maison : streaming (remend) + Shiki + KaTeX + `rehype-harden`/`sanitize` anti-XSS. Leçon LobeChat (GHSA-xq4x-622m-q8fq, XSS→RCE) : toujours sanitiser le contenu venant du LLM.
- **Build = copier** les patterns shadcn AI Elements (oct 2026, MIT, copy-paste, zéro dep) : `Trace` pour `/traces`, `Confirmation` pour l'approbation d'ordre. Ne PAS installer le package npm `ai-elements` (déprécié fin 11/2026).
- **Extend** notre client SSE maison : `id:` sur chaque event + `Last-Event-ID` + replay depuis `run_steps` (`GET /runs/{id}/events?after=`) + `POST /runs/{id}/stop`. Côté front : `@ag-ui/client` (54 Ko gzip) ou TanStack AI `@tanstack/ai-react` 1.0.2 (POC, cohérent avec notre stack TanStack).
- A11y du streaming : buffer d'annonce `aria-live` (~500 ms, ne pas annoncer chaque token), `role="alert"` sur les erreurs, modale d'approbation en vrai `role="dialog"` avec focus trap, tests NVDA manuels (axe ne couvre que 30-40 %).

## À NE PAS adopter (morts / dangereux / licence / SaaS) — vérifié le 14/11/2026

llm-guard (archivé 07/2026), Daytona (cœur fermé 06/2026), PyRIT (archivé 03/2026), AgentOps (abandon de fait), HumanLayer (SDK déprécié), aider et Roo Code (projets arrêtés en 2026), CrewAI (4 CVE RCE 2026), agno (3 CVE 2026), NeMo Guardrails (128 deps + télémétrie), Semgrep embarqué dans le produit (LGPL), TruffleHog en prod (AGPL + vérification réseau active), jina-embeddings-v5 (CC BY-NC, non commercial), Weave Router (Elastic License v2), crush (FSL, non OSI), MemPalace (benchmarks contestés), GPTCache (plus de release depuis 2024), RouteLLM (figé 2024), xgrammar côté client (tire torch/triton), detect-secrets (quasi statique), scrubadub (mort 2023), et tous les SaaS externes pour la privacy des prompts (Martian/Not Diamond, Cloudflare AI Gateway, Braintrust, LangSmith, Lakera Guard, LangCache managé, E2B/Modal/Vercel/Cloudflare en managed).
