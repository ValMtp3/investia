# 06 — Sécurité et légal

## Légal (⚠️ à confirmer si le projet change de nature)

Le projet est une **simulation personnelle à but éducatif**, utilisée par une seule personne, sans argent réel ni ordre réel. En France et en Europe, le conseil en investissement personnalisé est une activité réglementée (autorité : AMF, cadre européen : MiFID II). Ce projet reste hors de ce cadre **tant que** :

1. Il n'est pas ouvert à d'autres personnes.
2. Il n'exécute aucun ordre réel.
3. Il ne se présente pas comme un service de conseil.

Si l'un de ces trois points change, il faut demander l'avis d'un juriste avant d'aller plus loin. Cette note n'est pas un avis juridique.

Dans l'interface : mention permanente « Simulation, ceci n'est pas un conseil en investissement ».

## Secrets

| Règle | Pourquoi |
|---|---|
| Clés (OpenAI, données de marché, base) dans des variables d'environnement | Une clé dans le code finit tôt ou tard dans Git |
| Fichier `.env` exclu de Git, `.env.example` sans valeurs réelles | On documente sans exposer |
| Vérifier au démarrage que les clés requises sont présentes | Échec rapide et clair |
| Si une clé fuite : la révoquer tout de suite | Une clé exposée est considérée comme compromise |

## Accès

- Tout passe par Nginx Proxy Manager (déjà sur le VPS) puis Authelia (connexion, forward-auth). Aucune page ni API accessible sans être connecté. Les conteneurs de l'app ne publient aucun port public.
- Un seul compte utilisateur.
- Second facteur : **retiré le 07/11/2026 (D63, risque assumé)** — l'enregistrement TOTP exigeait un e-mail non envoyé par le VPS. Aujourd'hui : mot de passe seul. Si un jour un relais SMTP est configuré, remettre la 2FA (remettre `policy: 'two_factor'` dans `deploy/authelia/configuration.yml`).

## Données et entrées

- Toute entrée utilisateur est validée côté backend (schémas Pydantic).
- Requêtes SQL paramétrées (pas de texte concaténé) : évite l'injection SQL.
- Limitation du nombre de requêtes sur les points sensibles, notamment ceux qui appellent le modèle (coût).
- Les messages d'erreur ne révèlent ni clé, ni chemin, ni détail interne.

## Risques propres aux agents IA

| Risque | Mesure |
|---|---|
| **Injection de prompt** : un texte malveillant (ex. dans une actualité) tente de donner des ordres à l'IA | Le contenu externe est traité comme de la donnée, jamais comme une instruction ; les outils ont des droits limités |
| Dépense incontrôlée | Budget de coût et nombre de tours maximum par exécution |
| Chiffre inventé | Garde-fou « chaque nombre vient d'un outil » |
| Action non voulue | Aucun outil ne peut agir hors du portefeuille simulé ; validation humaine avant ordre |

## Revue de sécurité

Avant la mise en ligne (étape 4 bis de la roadmap) : revue complète avec le skill `security-review`.
