# 04 — Données de marché

## Principe

Offres **gratuites d'abord**. Les connecteurs sont isolés derrière une interface commune : changer de fournisseur ne touche pas le harness.

> **Connecteur** : un petit module qui sait parler à une source de données. Comme un adaptateur de prise : l'appareil reste le même, seul l'adaptateur change selon le pays.

## Sources retenues (vérifiées le 30 oct. 2026 — D28)

| Besoin | Source retenue | Pourquoi | Limites (oct. 2026) |
|---|---|---|---|
| Prix actions & ETF US (temps réel) | **Finnhub** (clé gratuite) | 60 appels/min, temps réel US, `quote`, `search`, `market-status` — testé OK le 31/10/2026 (D36) | Historique (candles), financials, forex, crypto, **Europe = payants** (testé : « no access »). 60/min partagés → cache Redis indispensable |
| Prix Europe (XETRA, Euronext) — quote delayed | **Yahoo Finance chart** (`query1.finance.yahoo.com/v8/finance/chart/SAP.DE`) | Testé OK le 31/10/2026 : intraday delayed + devise native (EUR), sans clé. ⚠️ API non officielle (ToS gris) : connecteur isolé, swappable | Delayed (~15 min), rate limits non documentés (429 vu en test), peut changer sans prévenir |
| Historique Europe (XETRA `.XETRA`, Euronext `.PA`) | **EODHD plan Sandbox $0** (clé gratuite sans CB, `EODHD_API_KEY`) | Couvre 60+ places dont `.XETRA`/`.PA`, EOD, 1 an d'historique, ToS propre (P8). Recherche sourcée : `docs/research/2026-10-31-alternatives-donnees-europe.md` | **20 appels/jour** (un 404 compte) → réservé aux rechargements d'historique. Secours : Alpha Vantage (25/j), marketstack (100/mois), Euronext CSV (delayed 15 min, rétention 24 h) |
| Historique actions/ETF US (graphiques, backtests) | **Cascade (D46)** : Yahoo chart → EODHD → **Twelve Data** → **Massive** | Chaque source est essayée dans l'ordre ; la première qui répond gagne, la légende du graphique nomme la source | Yahoo non officiel (429 vu le 01/11) ; EODHD 20 appels/jour ; Twelve Data Basic 800 crédits/jour (clôtures journalières, clé gratuite) ; Massive Stocks Basic 5 appels/min, 2 ans, US seulement (clé gratuite) |
| Crypto | **CoinGecko Demo** (clé gratuite) + **Binance public** en secours | CoinGecko : 1 000+ cryptos, news, Fear & Greed Index. Binance : prix temps réel sans clé (`data-api.binance.vision`), 1 200 weight/min | CoinGecko : 100 appels/min, 10 000 crédits/mois, fraîcheur ~60 s, attribution requise |
| Actualités financières | **Finnhub** `company-news` (par ticker) + `news` (marché général) | Inclus dans le free tier, 60/min, avec sentiment | Même limite 60/min que les quotes. NewsAPI.org / GNews free = dev-only, à éviter |
| Taux de change EUR/USD | **Frankfurter v2** (taux officiels BCE, sans clé) | `api.frankfurter.dev/v2/providers/ecb/rates` — fiable, keyless | Taux journaliers (référence BCE) |

**Écartés** : Alpha Vantage free (25 req/jour, trop limité), Twelve Data free (données différées 4 h), NewsAPI.org free (24 h de délai, dev-only). Yahoo/yfinance : écarté le 30/10 (non officiel), **réintégré le 31/10 pour l'Europe uniquement** (P8) car aucune source gratuite officielle ne couvre l'Europe — isolé derrière son propre connecteur. Stooq : écarté temporairement (anti-bot, voir ci-dessus).

> Règle : pas de liste d'actifs initiale — tu ajoutes ce que tu veux dans le dashboard (Q5). Chaque actif ajouté consomme la limite de 60 appels/min de Finnhub : le cache Redis fait tenir ça (prix refresh 60 s max).

## Stratégie multi-sources

Un connecteur par source, derrière une interface commune. Si Finnhub tombe en panne : erreur claire, jamais de chiffre inventé. En secours crypto : Binance public.

**Cascade pour l'historique US (D46, étape 4.4d)** : le service essaie les sources dans l'ordre (`market/router.py`, `pick_sources`). Une source sans clé est sautée. Une source qui répond « trop de requêtes » (429) est mise en pause 10 minutes (clé Redis `cooldown:<source>`) pour ne pas aggraver le blocage. Historique mis en cache 24 h. Si toutes échouent : une erreur qui liste chaque tentative. **Repli d'affichage** : dans `/market/stream`, un prix en direct qui échoue est remplacé par la dernière clôture de l'historique, marquée `is_close` (« clôture du 30/10 ») ; l'agent et le portefeuille ne l'utilisent pas. Aucun contournement d'anti-robot (Stooq reste écarté).

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
