# 10 — Glossaire

| Mot | Explication simple |
|---|---|
| **Harness** | Tout ce qui entoure le modèle d'IA (outils, mémoire, règles, tests, journaux). Le modèle est le moteur, le harness est la voiture. |
| **Agent** | Une IA qui peut décider d'utiliser des outils et enchaîner plusieurs étapes, au lieu de répondre en une fois. |
| **Boucle d'agent** | Réfléchir, appeler un outil, lire le résultat, recommencer. Comme un enquêteur qui interroge des témoins. |
| **Outil (tool)** | Une fonction que l'IA peut demander d'exécuter (ex. donner un prix). |
| **Garde-fou (guardrail)** | Une vérification en code sur la réponse, avant de la montrer. Un relecteur avant publication. |
| **Eval** | Un test automatique qui note la qualité de l'agent. |
| **Trace** | Le journal détaillé d'une exécution, rejouable. La boîte noire d'un avion. |
| **Run** | Une exécution complète de l'agent pour une question. |
| **Token** | Un morceau de texte (environ un mot ou une partie de mot). Le modèle se facture et se limite en tokens. |
| **Fenêtre de contexte** | La quantité maximale de texte que le modèle lit d'un coup. Comme la taille d'un bureau : au-delà, des papiers tombent. |
| **Prompt** | Les instructions écrites données au modèle. |
| **Injection de prompt** | Un texte malveillant caché dans une donnée (ex. une actualité) qui essaie de donner des ordres à l'IA. |
| **MCP** | Model Context Protocol : standard pour brancher des outils à une IA. Une prise universelle. Spec 2026-07-28 : plus de session, scale horizontal facile. |
| **Human-in-the-loop** | Un humain valide avant qu'une action ait lieu. |
| **Multi-agents** | Plusieurs agents spécialisés qui collaborent. |
| **ETF** | Un panier d'actions qui se vend comme une seule action. |
| **Portefeuille simulé (papier)** | Un portefeuille avec de l'argent fictif, pour tester sans risque. |
| **Connecteur** | Un module qui sait parler à une source de données. Un adaptateur de prise. |
| **Cache** | Garder une réponse en mémoire pour ne pas redemander la même chose. Noter un numéro au lieu de rechercher l'annuaire à chaque fois. |
| **TTL** | *Time To Live* : la durée de vie d'une donnée en cache. Passé ce délai, elle est jetée et on la redemande. Comme la date limite d'un yaourt. |
| **Biais de regard vers l'avenir** | Tester sur le passé avec des informations qui n'existaient pas encore à l'époque : l'agent « triche » sans le savoir. |
| **OIDC** | OpenID Connect : standard où l'app elle-même demande à un service d'identité si la personne est connectée. Pas utilisé ici : on passe par le forward-auth. |
| **Forward-auth** | Le reverse proxy (NPM) demande à Authelia « cette personne est connectée ? » **avant** de laisser passer la requête vers l'app. Comme un vigile à l'entrée de l'immeuble : l'app n'a rien à vérifier. |
| **Authelia** | Service d'authentification auto-hébergé léger (~50 Mo), utilisé ici pour la connexion. Alternative à Authentik pour un usage solo. |
| **Nginx Proxy Manager (NPM)** | Interface web pour gérer les proxy inverses nginx (domaines, certificats HTTPS). Déjà installé sur le VPS, notre app passe derrière. |
| **LiteLLM** | Proxy self-hosté qui unifie 100+ fournisseurs de modèles (OpenAI, Mistral...) derrière une seule API, avec suivi des coûts et budgets. |
| **Mistral Large 4** | Gros modèle de Mistral (entreprise française), utilisé ici pour les analyses approfondies. |
| **Multi-provider** | Utiliser plusieurs fournisseurs de modèles (ici OpenAI + Mistral) plutôt qu'un seul, pour comparer qualité et coût. |
| **Docker / Compose** | Docker met chaque programme dans une boîte isolée ; Compose lance toutes les boîtes ensemble. |
| **Healthcheck** | Une petite adresse que Docker interroge pour savoir si un service va bien. Ici : `/health` = « le programme tourne », `/ready` = « la base et Redis répondent ». Comme prendre le pouls, puis faire un bilan de santé. |
| **Reverse proxy** | Le portier : reçoit les visiteurs, gère le HTTPS, les envoie au bon service. Ici, c'est le Nginx Proxy Manager déjà présent sur le VPS. |
| **VPS** | Un serveur loué que tu gères toi-même. |
| **ADR** | Fiche courte qui note une décision et son pourquoi. |
| **AMF / MiFID II** | Autorité des marchés financiers (France) / règlement européen qui encadre le conseil en investissement. |
| **Jev** | Modèle de décision « System One » (TypeSafe AI, 2026) : reçoit un état + des questions typées, retourne des probabilités calibrées, pas du texte. 20-200x plus rapide et bien moins cher qu'un LLM. |
| **SSE** | Server-Sent Events : le serveur pousse des mises à jour au navigateur sur une connexion HTTP simple. Comme une sonnette, plutôt que d'appeler toutes les 5 min « il y a du nouveau ? ». |
| **A2A** | Agent2Agent : protocole standard (Linux Foundation, v1.0 en 2026) pour que des agents se découvrent et se délèguent des tâches. |
| **AG-UI** | Agent-User Interaction Protocol (CopilotKit) : stream les événements d'un agent (tokens, outils, état) vers un frontend React, avec interrupts pour la validation humaine. |
| **Semantic cache** | Cache qui renvoie une ancienne réponse quand la question est sémantiquement proche, grâce à une recherche vectorielle. Économise 25-40 % des appels LLM. |
| **Prompt caching** | Cache automatique des tokens répétés d'un prompt (instructions au début) : -90 % sur cette partie chez OpenAI. |
| **pgvector** | Extension PostgreSQL qui ajoute les vecteurs (embeddings) et la recherche par similarité, directement dans la base. Elle demande l'image Docker `pgvector/pgvector`, pas `postgres` tout court. |
| **Embedding** | Représentation numérique d'un texte (un vecteur de nombres) qui permet de mesurer la similarité entre deux textes. |
| **OpenTelemetry GenAI** | Standard de traces pour l'IA (`gen_ai.*`) : chaque appel de modèle, outil, token devient une span tracée comme n'importe quelle requête. |
| **Migration (Alembic)** | Un fichier versionné qui décrit un changement du schéma de la base (ajouter une table, une colonne). Comme le carnet d'entretien d'une voiture : on rejoue les étapes dans l'ordre. |
| **CI/CD** | Intégration continue : à chaque envoi de code, des robots lancent lint, tests et build. Comme un contrôle qualité automatique en bout de chaîne. |
| **uv** | Gestionnaire de paquets et de projet Python écrit en Rust (2026) : remplace pip, venv, poetry. Installe tout en moins d'une minute. |
| **Ruff** | Linter + formateur Python en un seul outil Rust (2026) : remplace flake8, black, isort. |
| **DeepEval** | Framework d'evals LLM en Python, style pytest (2026). |
| **Promptfoo** | CLI d'evals et de red teaming LLM en YAML (2026). |
