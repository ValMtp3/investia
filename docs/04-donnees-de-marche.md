# 04 — Données de marché

## Principe

Offres **gratuites d'abord**. Les connecteurs sont isolés derrière une interface commune : changer de fournisseur ne touche pas le harness.

> **Connecteur** : un petit module qui sait parler à une source de données. Comme un adaptateur de prise : l'appareil reste le même, seul l'adaptateur change selon le pays.

## Sources retenues (vérifiées le 30 oct. 2026 — D28)

| Besoin | Source retenue | Pourquoi | Limites (oct. 2026) |
|---|---|---|---|
| Prix actions & ETF (US ; couverture Europe en temps réel à vérifier, Q9) | **Finnhub** (clé gratuite) | 60 appels/min, temps réel US, `quote`, `search`, `market-status`, profils, earnings — le plus fiable en gratuit | Historique (candles), financials, forex, crypto = **payants**. 60/min partagés entre tous les tickers → cache Redis indispensable |
| Historique actions/ETF (graphiques, backtests) | **Stooq** (CSV, clé gratuite via CAPTCHA) | 12 000+ titres globaux (US, Europe, indices, forex), gratuit, fiable | Clé requise depuis début 2026, quota journalier. Alternative : **Massive** (ex-Polygon) Basic $0 = EOD 2 ans, 5 appels/min |
| Crypto | **CoinGecko Demo** (clé gratuite) + **Binance public** en secours | CoinGecko : 1 000+ cryptos, news, Fear & Greed Index. Binance : prix temps réel sans clé (`data-api.binance.vision`), 1 200 weight/min | CoinGecko : 100 appels/min, 10 000 crédits/mois, fraîcheur ~60 s, attribution requise |
| Actualités financières | **Finnhub** `company-news` (par ticker) + `news` (marché général) | Inclus dans le free tier, 60/min, avec sentiment | Même limite 60/min que les quotes. NewsAPI.org / GNews free = dev-only, à éviter |
| Taux de change EUR/USD | **Frankfurter v2** (taux officiels BCE, sans clé) | `api.frankfurter.dev/v2/providers/ecb/rates` — fiable, keyless | Taux journaliers (référence BCE) |

**Écartés** : Yahoo/yfinance (non officiel, « borrowed time », ToS gris), Alpha Vantage free (25 req/jour, trop limité), Twelve Data free (données différées 4 h), NewsAPI.org free (24 h de délai, dev-only).

> Règle : pas de liste d'actifs initiale — tu ajoutes ce que tu veux dans le dashboard (Q5). Chaque actif ajouté consomme la limite de 60 appels/min de Finnhub : le cache Redis fait tenir ça (prix refresh 60 s max).

## Stratégie multi-sources

Un connecteur par source, derrière une interface commune. Si Finnhub tombe en panne : erreur claire, jamais de chiffre inventé. En secours crypto : Binance public. En secours historique : Stooq ↔ Massive.

## Contraintes du gratuit

| Contrainte | Conséquence dans la conception |
|---|---|
| Limite d'appels | **Cache Redis** avec TTL par type de donnée (prix : 60 s, historique : 1 h, news : 15 min) |
| Données parfois différées | Chaque donnée porte son **horodatage**, affiché au dashboard |
| Marchés actions fermés la nuit et le week-end | L'agent doit savoir dire « marché fermé, dernier cours à telle heure » |
| Fournisseur en panne | Erreur claire, jamais de chiffre inventé en remplacement |

> On ajoute un **cache sémantique LLM** (Redis vector) : une question proche d'une question déjà posée renvoie la réponse en cache sans appeler le modèle.

## Format commun d'une donnée

Chaque donnée renvoyée par un connecteur contient : valeur, devise, source, horodatage, et un indicateur « différé ou non ». C'est ce qui permet au garde-fou de vérifier les chiffres et la fraîcheur.

## Rafraîchissement

**SSE (Server-Sent Events)** : le backend pousse les prix au dashboard dès qu'il les reçoit (ou toutes les N secondes côté serveur, selon la limite du fournisseur). Le client ne poll jamais. C'est comme la sonnette vs appeler toutes les 5 minutes « il y a du nouveau ? ».

## Sécurité des clés

Les clés API vivent dans des variables d'environnement, jamais dans le code ni dans Git. Voir `06-securite-et-legal.md`.
