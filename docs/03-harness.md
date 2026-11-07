# 03 — Le harness

C'est le cœur du projet. Chaque section est une brique à construire à la main.

## 1. Boucle d'agent

**Idée** : le modèle ne répond pas d'un coup. Il réfléchit, demande un outil, lit le résultat, puis recommence jusqu'à avoir assez d'éléments. Comme un enquêteur qui interroge des témoins avant de conclure.

```text
boucle (max N tours) :
    réponse = modèle(messages, outils disponibles)
    si réponse demande des outils :
        exécuter les outils, ajouter les résultats aux messages
    sinon :
        sortir avec la réponse finale
```

Règles :
- **Nombre de tours maximum** et **budget de coût maximum** par exécution (sinon une boucle infinie coûte cher).
- Chaque erreur d'outil est renvoyée au modèle sous forme lisible, jamais avalée.
- Les appels aux modèles passent par le gateway **LiteLLM** (D29). L'API exacte de chaque fournisseur est à confirmer avec la doc à jour.

## 2. Trois niveaux de modèle

| Niveau | Rôle | Exemples de tâches | Modèle (oct. 2026) | Prix (par M tokens) |
|---|---|---|---|---|
| **Décision** | Décisions binaires/catégorielles, ultra-rapide et quasi gratuites | Router gros/petit, classer la question, garde-fou « la réponse est-elle sûre ? », juge d'eval simple | **elephant-1** (Baseten, D44) | gratuit via OpenRouter (`baseten/elephant-1:free`) |
| Petit | Tâches simples et rapides | Résumer une actualité, extraire des entités | **GPT-6 Luna** (OpenAI) | $0.10 input / $0.50 output (cached $0.01) |
| Gros | Raisonner, synthétiser | Analyse d'un actif, recommandation finale | **Mistral Large 4** (Mistral — appelé rarement) | $1.36 input / $4.18 output (cached $0.14) |

> **Multi-provider** : deux fournisseurs de chat (OpenAI + Mistral) derrière le gateway **LiteLLM** (D29) : proxy self-hosté gratuit, une seule API compatible OpenAI, budget controls et cost tracking intégrés. ⚠️ Le modèle de décision n'est pas un modèle de chat : il passe par LiteLLM sur /v1/systemone (Q10 résolu, D37/D44).

> **elephant-1** n'est pas un LLM : il ne rédige pas de texte. Tu lui envoies un état (JSON) + des questions typées (« cette réponse contient-elle un chiffre non sourcé ? »), il retourne des **probabilités calibrées** sur des réponses prédéfinies (oui/non, A/B/C) avec un score de confiance. Ton code agit directement sur le résultat. 20-200x plus rapide qu'un LLM, gratuit via OpenRouter (octobre 2026). Si la confiance est basse, on peut escalader vers un LLM.
>
> Variante « maison » à tester : n'importe quel LLM peut faire de la décision en lisant les *logprobs* du prochain token sur des choix numériques (voir le papier « LLM-as-Jev », 2026).

Les noms de modèles sont **dans un fichier de configuration**, jamais dans le code. On pourra ainsi les changer et mesurer l'effet avec les evals.

Le **routeur** est assuré par elephant-1. Au début : questions simples en dur. Plus tard : le modèle de décision apprend du feedback + evals.

**Optimisation des coûts** (budget 10-20 €/mois) :
- Prompt caching automatique (prompts ≥ 1024 tokens, contenu statique au début) : -90 % sur le répété.
- **Cache sémantique** (Redis vector) : une question sémantiquement proche d'une ancienne renvoie la réponse cachée, zéro appel LLM. Hit rate typique 25-40 %.
- Batch API pour les evals (sortie à -50 %).
- Budget max par exécution, bloqué en code.

## 3. Outils

Un outil = une fonction Python avec une description et un schéma d'entrée strict.

| Outil | Rôle | Étape |
|---|---|---|
| `get_quote` | Prix actuel d'un actif | 1 |
| `get_history` | Historique de prix | 1 |
| `get_indicators` | Moyennes mobiles, volatilité, calculées par le code | 1 |
| `get_news` | Actualités récentes sur un actif | 1 |
| `get_portfolio` | État du portefeuille simulé | 4 |
| `simulate_order` | Ordre fictif, avec validation humaine | 5 |
| `recall_memory` / `save_memory` | Mémoire longue | 3 |

Règles : entrées validées (Pydantic), sorties **avec source et horodatage**, aucun outil n'accède à autre chose que ce pour quoi il est prévu.

## 4. Garde-fous (guardrails)

Un garde-fou vérifie la réponse **avant** qu'elle te soit montrée. Comme un relecteur avant publication.

| Garde-fou | Vérifie | Si échec |
|---|---|---|
| Format | La réponse respecte le schéma (thèse, risques, confiance, sources) | Nouvelle tentative |
| Chiffres | Chaque nombre cité existe dans une sortie d'outil | Correction ou refus |
| Fraîcheur | Les données ne sont pas trop vieilles | Avertissement visible |
| Langage interdit | Pas de « gain garanti », « sans risque » | Réécriture |
| Avertissement | Mention « simulation, pas un conseil » présente | Ajout automatique |
| Budget | Coût et tours sous la limite | Arrêt propre |

Les garde-fous sont du **code**, pas des demandes polies dans le prompt. Un prompt se contourne, une vérification Python non. Jev peut s'ajouter en renfort (ex. « cette réponse a-t-elle l'air sûre ? »), jamais à la place des vérifications en code (chiffres, format, budget).

## 5. Mémoire et contexte

- **Court terme** : la conversation en cours. Le modèle ne peut lire qu'une quantité limitée de texte (la *fenêtre de contexte*, ~1M tokens sur les modèles 2026). On résume ou on retire les vieux messages avant d'atteindre la limite.
- **Long terme** : profil de risque, préférences, faits utiles, stockés dans `memories` **avec une colonne `embedding` (pgvector)** pour la recherche sémantique directement dans PostgreSQL. À notre échelle (quelques milliers de souvenirs), pgvector suffit — pas besoin de Qdrant.

## 6. Évaluations (evals)

Des tests automatiques qui notent la qualité de l'agent. Sans eux, on améliore à l'aveugle.

| Type | Exemple |
|---|---|
| Déterministe | Pour « prix de BTC », l'agent appelle bien `get_quote` |
| Garde-fous | Une réponse avec un chiffre inventé est bien bloquée |
| Juge IA | Un petit modèle note la clarté et la justification (à calibrer, il peut être biaisé) |
| Portefeuille | Les conseils rejoués sur le passé battent-ils un simple ETF de référence ? |

⚠️ Piège du rejeu sur le passé : l'agent ne doit voir que les données **disponibles à la date simulée**. Sinon il « triche » sans le savoir (*biais de regard vers l'avenir*).

Une commande lance tout le jeu d'evals, et les scores sont enregistrés pour voir l'évolution.

## 7. Observabilité (traces)

Chaque exécution enregistre : messages, outils appelés (entrée, sortie), tokens, coût, durée, décisions des garde-fous, spans **OpenTelemetry GenAI** (`gen_ai.*` — le standard 2026). Comme la boîte noire d'un avion : en cas d'erreur, on rejoue ce qui s'est passé. Export d'abord vers PostgreSQL, Langfuse self-hosted plus tard si besoin.

## 8. Validation humaine (étape 5)

Avant un ordre simulé, l'agent s'arrête et te demande ton accord dans le dashboard. Pas de réponse = pas d'ordre. Côté frontend, AG-UI gère ça nativement (événement `interrupt` = bouton « valider »).

## 9. Protocoles modernes (étape 5)

La stack de protocoles agent 2026 (Linux Foundation / AAIF) :

| Protocole | Rôle | Quand |
|---|---|---|
| **MCP** (spec 2026-07-28) | Brancher des outils à l'agent (prise universelle). Sessions supprimées → scale horizontal facile | Étape 5 : exposer nos outils marché comme serveur MCP |
| **A2A** v1.0 | Communication agent ↔ agent (découverte, délégation). 150+ orgs, intégré Google/Microsoft/AWS | Étape 6 : multi-agents qui se parlent via A2A |
| **AG-UI** (CopilotKit) | Stream agent → frontend (17 event types, SSE, état partagé, interrupts human-in-the-loop) | Étape 4 : le chat du dashboard |

## 10. Multi-agents + comparaison frameworks (étape 6)

Plusieurs agents spécialisés (analyste, gestionnaire de risque, rédacteur) qui communiquent en A2A. On ne le fait qu'**après** avoir des evals solides.

À la même étape : **reconstruire le même harness avec LangGraph, Pydantic AI et OpenAI Agents SDK**, puis comparer avec les evals (qualité, coût, latence). Sans cette comparaison, on ne sait pas ce que le harnais maison apporte.
