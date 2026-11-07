# Alternatives gratuites aux données boursières européennes — 31 octobre 2026

> Recherche pour l'étape 1.2 (outils `get_quote` / `get_history` de l'agent), après le constat D36 : **Finnhub gratuit = US uniquement, l'Europe est payante** (testé le 31/10/2026, voir `docs/STATUS.md` et `docs/09-decisions.md`).
>
> Critère : HTTP pur depuis Python (pas de navigateur, pas de JS), actions et ETF européens (XETRA `.DE`, Euronext Paris `.PA`), prix même delayed + historique.
>
> Méthode : chaque affirmation est sourcée vers une **page primaire** (docs officielles, pages pricing, pages légales) consultée le 31/10/2026. Tests réalisés ce jour : Stooq bloqué par anti-bot (voir §3.15). **Aucune clé API dans ce fichier.**

## 1. Tableau comparatif (offre gratuite au 31/10/2026)

| Source | XETRA `.DE` / `.XETRA` | Euronext Paris `.PA` | Temps réel / delayed | Historique gratuit | Limite gratuite | Clé API | ToS |
|---|---|---|---|---|---|---|---|
| **Yahoo Finance chart API** (référence, déjà en place) | ✅ | ✅ | Delayed 15 min + intraday | Très long (`range=max`, ~1970) | Non documentée, throttling | Non (crumb/cookie parfois) | ⚠️ Grise : pas d'API officielle |
| **EODHD** — plan Sandbox $0 | ✅ (`.XETRA`) | ✅ (`.PA`) | EOD uniquement (clôture) | **1 an** | **20 appels/jour** (+500 bonus) ; 1 requête = 1 appel même un 404 | Oui, gratuite sans CB | ✅ Propre (usage perso) |
| **marketstack** — plan Free $0 | ✅ (72+ places) | ✅ | EOD uniquement | 1 an | **100 requêtes/mois** | Oui, gratuite | ✅ Propre (non-commercial) |
| **Alpha Vantage** — clé gratuite | ✅ (daily/weekly/monthly globaux) | ✅ | Daily = EOD ; intraday/temps réel = US (premium) | **25+ ans** | **25 requêtes/jour** | Oui, gratuite | ✅ Propre |
| **Massive (ex-Polygon)** — Stocks Basic $0 | ❌ US uniquement | ❌ | EOD | 2 ans | 5 appels/min | Oui, gratuite | ✅ Propre |
| **Twelve Data** — Basic $0 | ❌ en free (XETR = plan Grow 79 $/mois) | ❌ en free (Euronext Paris = plan Pro 229 $) | Free = 3 marchés (US/forex/crypto) ; EOD global en Grow, EU temps réel en Pro | Selon plan | 800 crédits/jour | Oui, gratuite | ✅ Propre |
| **Tiingo** | ❌ (US + Chine) | ❌ | — | — | **Pas de tier gratuit** (30 $/mois) | Oui | ✅ Propre |
| **Euronext (officiel)** | ❌ (Euronext ne couvre pas Xetra) | ✅ | **Delayed 15 min gratuit** (obligation MiFID II) : view service + CSV post-trade | CSV : rétention ≥ 24 h seulement ; historique long = payant | View/CSV publics gratuits | View/CSV : non ; Data Shop : compte | ✅ Propre (gratuit = exigence réglementaire) |
| **Deutsche Börse** | ⚠️ Pas d'API gratuite officielle temps réel/delayed (A7/OptiQ payants) ; Public Data Set AWS (1 min Xetra) **déprécié** | ❌ | Site boerse-frankfurt.de : delayed 15 min (endpoint interne non documenté) | AWS PDS : 1-min, non maintenu | PDS : illimité (S3 public) | PDS : non | ✅ PDS propre mais déprécié ; site = ⚠️ gris |
| **Nasdaq Data Link (ex-Quandl)** | ❌ (datasets gratuits = macro/éco ; WIKI delisted, Sharadar premium) | ❌ | ❌ | Datasets gratuits seulement | ~50 000 appels/jour (free tier) | Oui, gratuite | ✅ Propre |
| **OpenFIGI (Bloomberg)** | ✅ mapping d'identifiants (pas de prix) | ✅ | — | — | Sans clé ~25 req/min (10 jobs) ; clé gratuite = plus | Non (clé gratuite optionnelle) | ✅ Propre (open) |
| **TradingView** | ❌ pas d'API data publique | ❌ | — | — | — | — | ⚠️ Grise : scraping non officiel interdit |
| **Investing.com** | ❌ pas d'API | ❌ | — | — | — | — | 🔴 ToS interdit le scraping |
| **justETF / extraETF** | ⚠️ quotes ETF XETRA via endpoints internes non documentés | ⚠️ idem | ⚠️ | ⚠️ | Non documentée | Non | ⚠️ Grise : pas d'API publique officielle |
| **Stooq** | ✅ (CSV officiels `.de`) | ✅ (`.pa`) | EOD + intraday selon `i=` | Long | Illimité théorique | Non | 🔴 **Bloqué en pratique** : anti-bot PoW, « Access denied » (testé 31/10/2026) |

## 2. Verdict

**Meilleure alternative « propre » à Yahoo pour l'Europe en gratuit : EODHD (plan Sandbox $0).**
Pourquoi : clé gratuite sans carte bancaire, ToS clair (usage perso), et le plan gratuit couvre **tous les tickers de 60+ places, donc `.XETRA` et `.PA`**, en EOD avec 1 an d'historique — 20 appels/jour. C'est la seule source gratuite avec clé qui couvre à la fois XETRA et Euronext Paris en historique, avec un contrat propre.

**Pour Euronext Paris spécifiquement**, la source officielle et gratuite est **Euronext elle-même** : données delayed 15 min gratuites (obligation MiFID II), en view service sur `live.euronext.com` et en fichiers CSV post-trade sur `marketdata.euronext.com` (HTTP pur, rétention ≥ 24 h). Le temps réel et l'historique long restent payants (Euronext Web Services, sur contrat).

**Pour XETRA**, il n'existe **aucune API officielle gratuite** en temps réel ou delayed : le portail développeur de Deutsche Börse exige un onboarding (A7/OptiQ payants), et le Public Data Set AWS (données 1 minute Xetra/Eurex, S3 public sans clé) est **déprécié et non maintenu**. En pratique XETRA passe par Yahoo (`.DE`) + EODHD (`.XETRA`).

**Cumul recommandé avec Yahoo** (Yahoo chart API reste la seule source gratuite couvrant `.DE`/`.PA` en intraday/delayed, mais non officielle) :

1. **Yahoo chart API** — prix delayed/intraday `.DE` / `.PA` (déjà en place, D36).
2. **EODHD free** — historique EOD propre, toutes places Europe (20 appels/jour : à réserver aux rechargements d'historique, pas aux quotes fréquentes).
3. **Euronext (CSV MiFID II / Delayed Data API)** — delayed 15 min officiel pour Euronext Paris.
4. **Alpha Vantage free** — historique daily long terme (25+ ans) Europe, en secours (25 req/jour).
5. **marketstack free** — deuxième source EOD (100 req/mois) pour recouper EODHD.
6. **OpenFIGI** — mapping ISIN/ticker → FIGI + code exchange (ex. `.PA`, `.DE`), gratuit, pour normaliser les symboles.
7. **Frankfurter** — taux de change (déjà en place).

## 3. Détails par source (sources primaires)

### 3.1 Yahoo Finance chart API — référence actuelle, ToS grise
- Endpoint non officiel : `https://query1.finance.yahoo.com/v8/finance/chart/AIR.PA` (fonctionne, testé dans le projet — D36). Couvre `.DE` et `.PA`, delayed 15 min + intraday, historique long via `range`.
- Yahoo ne publie aucune doc pour cet endpoint et ses conditions interdisent le scraping automatisé : https://legal.yahoo.com/us/en/yahoo/terms/index.html
- ⚠️ Risque : rate-limit / crumb requis / changement sans préavis. C'est pourquoi on cherche des alternatives propres.

### 3.2 EODHD — plan Sandbox $0 ✅ meilleure alternative Europe
- Pricing : « Sandbox Free Package $0/mo » — https://eodhd.com/pricing
- Doc officielle de l'endpoint EOD : « On the free plan you get the same endpoint for **any ticker**, but only the **past year** of history and **20 API calls a day** » ; « Free plan — your own key, no credit card required, 20 API calls a day, plus 500 welcome-bonus calls. Past year of data, personal use » ; la clé `demo` ne marche que sur 6 tickers US (AAPL.US, TSLA.US, BTC-USD.CC, VTI.US, AMZN.US, EURUSD.FOREX) — https://eodhd.com/financial-apis/api-for-historical-data-and-volumes
- Couverture : 60+ places, 150 000+ tickers, dont XETRA (`.XETRA`) et Euronext Paris (`.PA`) — https://eodhd.com/list-of-stock-markets
- Live/delayed et intraday = payants. ToS propre (usage perso).

### 3.3 marketstack — plan Free $0
- « Free forever. $0 per month … **100 Requests / mo** … **End-of-Day Data** … **1 Year History** … Splits & Dividends … Non-Commercial Use » — https://marketstack.com/pricing
- Couverture EOD : 125 000+ tickers sur 72+ places (docs révisées septembre 2026), places européennes incluses — https://marketstack.com/documentation
- Clé API gratuite requise. EOD uniquement en free ; intraday/temps réel = plans payants.

### 3.4 Alpha Vantage — clé gratuite
- « the majority of our API endpoints can be accessed for free … standard API usage limit (**25 API requests per day**) » ; premium dès 49,99 $/mois — https://www.alphavantage.co/premium/
- « This suite of APIs provides **global equity data** in 4 different temporal resolutions: daily, weekly, monthly, and intraday, with **25+ years** of historical depth… For **US markets specifically** … deep NBBO » — https://www.alphavantage.co/documentation/
- Donc : daily/weekly/monthly = monde entier (places européennes incluses, suffixes type `.PA`/`.DE`) ; intraday/temps réel = US. 25 req/jour en gratuit.

### 3.5 Massive (ex-Polygon.io) — Stocks Basic $0 ❌ US only
- « Stocks Basic $0/month … **All US Stocks Tickers** … 5 API Calls / Minute … 2 Years Historical Data … End of Day Data » ; tous les plans stocks listés sont « All US Stocks Tickers » — https://massive.com/pricing
- Le tier gratuit ne couvre donc **pas** l'Europe.

### 3.6 Twelve Data — Basic $0 ❌ Europe hors free
- Pricing : « Basic $0 … API credits 8 (800 a day) … Daily limits 800/day … Markets **3** » — https://twelvedata.com/pricing
- Page exchanges : « Frankfurt Stock Exchange (Xetra) **XETR** Germany EOD … **Grow** » et Euronext (Paris, Lisbonne, etc.) « … **Pro** » — https://twelvedata.com/exchanges
- Donc XETRA = plan Grow (79 $/mois, EOD global), Euronext Paris = plan Pro (229 $/mois, temps réel EU). Le free (3 marchés) est US/forex/crypto.

### 3.7 Tiingo — pas de tier gratuit, pas d'Europe ❌
- « It is simply $30/month … for individuals » (pas de plan $0) — https://www.tiingo.com/about/pricing
- Couverture EOD : « US & Chinese markets », 65 000+ equities/funds/ETF, historique depuis 1962 — https://www.tiingo.com/products/end-of-day-stock-price-data

### 3.8 Euronext (officiel) — delayed 15 min gratuit pour Euronext Paris ✅
- « Euronext is required to make **delayed data available free of charge**. We offer a **view service** as well as a **file download service** » — https://www.euronext.com/en/data/market-data/mifid-ii-compliant-data
- « Delayed post-trade data files are available to download in **.csv** … maximum time delay of **15 minutes** … remains available for **at least 24 hours** » — https://marketdata.euronext.com/data-reporting-service/trades-file
- « The Euronext **Delayed Data API** offers easy access to market data for individual investors … quotes, last price, trades, performance and reference data » — https://live.euronext.com/en/datashop/delayed-data
- Temps réel / historique via **Euronext Web Services** (web API) = **payant, sur contrat** (« Market Data Fees and Policies », price lists par place) — https://www.euronext.com/en/data/how-access-market-data/web-services et https://www.euronext.com/en/data/pricing-specs-agreements
- Ne couvre pas XETRA (Euronext = Paris, Amsterdam, Bruxelles, Dublin, Lisbonne, Milan, Oslo).

### 3.9 Deutsche Börse — pas d'API gratuite officielle Xetra ⚠️
- Portail développeur : « Sign up to an easy to use developer portal and profit from a **range of free financial APIs** » (inscription requise ; catalogue sur la console) — https://developer.deutsche-boerse.com/ et https://console.developer.deutsche-boerse.com/apis
- Market data Xetra/Eurex temps réel = produits payants (A7 / OptiQ MDG) — https://www.deutsche-boerse.com/dbg-en/markets-services/ps-technology/ps-api-platform
- **Deutsche Börse Public Data Set** (AWS Open Data) : « trade data aggregated to **one minute** intervals from **Eurex and Xetra** », buckets S3 publics sans compte (`aws s3 ls --no-sign-request s3://deutsche-boerse-xetra-pds/`) — mais **« Deprecated … will no longer maintain this dataset »** — https://registry.opendata.aws/deutsche-boerse-pds/
- Le site boerse-frankfurt.de affiche des cours delayed 15 min, mais via des endpoints internes non documentés (ToS grise).

### 3.10 Nasdaq Data Link (ex-Quandl) — pas de prix Europe en gratuit ❌
- « Getting started with Nasdaq Data Link is seamless, easy and **free** » : compte gratuit + clé API gratuite = **datasets gratuits uniquement** (macro, éco, indicateurs) — https://data.nasdaq.com/
- Limites free tier : ~50 000 appels/jour, 2 000/10 min, 300/10 s, concurrence 1 — https://docs.data.nasdaq.com/
- Les datasets de prix actions (WIKI delisted ; Sharadar payant) ne sont pas gratuits → inutile pour XETRA/Euronext en temps réel.

### 3.11 OpenFIGI (Bloomberg) — mapping d'identifiants, pas de prix ℹ️
- « The OpenFIGI API allows **mapping** from third-party identifiers to FIGIs … The API is **free and open to the public**, though unauthenticated traffic will be subject to a lower rate-limit » ; « free to use **without daily, weekly or monthly limitations** » avec clé gratuite — https://www.openfigi.com/api/documentation et https://www.openfigi.com/api/overview
- Sans clé : ~25 req/min, 10 jobs par requête. Couvre le monde entier (exchCode, MIC) → utile pour résoudre ISIN → ticker `.PA` / `.DE`. **Ne fournit aucun prix.**

### 3.12 TradingView — pas d'API data publique ⚠️
- FAQ officielle : « **No.** Widgets can only display data provided by TradingView, and we don't have an API for feeding your own data into them. … Our REST API is meant for **brokers** who want to be supported on our trading platform. » — https://www.tradingview.com/support/solutions/43000474413-i-need-access-to-your-api-in-order-to-get-data-or-indicator-values/ et https://www.tradingview.com/widget-docs/faq/data/
- Les librairies type `tvdatafeed` scrapent le site : non officiel, ToS grise.

### 3.13 Investing.com — pas d'API, scraping interdit 🔴
- Support officiel : « Do You Offer API Access at Investing.com? » → pas d'API directe, données servies via web/apps — https://www.investing-support.com/hc/en-us/articles/115005473825-Do-You-Offer-API-Access-at-Investing-com
- CGU : « with regard to any Market Information displayed on the Platform, you are prohibited from … » (scraping/redistribution) — https://cdn.investing.com/about-us/terms_and_conditions.pdf

### 3.14 justETF / extraETF — pas d'API publique officielle ⚠️
- Aucun endpoint documenté pour les tiers ; le site s'appuie sur des endpoints internes non documentés (ex. `https://www.justetf.com/api/etfs/{ISIN}/quote` renvoyant un prix XETRA) — constatés le 31/10/2026 sur https://www.justetf.com/en/ ; des scrapers tiers (Apify, parse.bot) confirment l'absence d'API officielle. extraETF : pas d'API publique non plus (offre B2B payante) — https://extraetf.com/
- Données ETF Europe très riches, mais contrat inexistant → ToS grise, à éviter comme source primaire.

### 3.15 Stooq — gratuit sur le papier, bloqué en pratique 🔴
- CSV officiels gratuits : `https://stooq.com/q/d/l/?s=sap.de&i=d` (couvre `.de`, `.pa`, historique long, pas de clé).
- **Testé le 31/10/2026** : anti-bot PoW, « Access denied » même en résolvant le challenge, et le fetch automatisé est bloqué (« the site blocked automated access ») — https://stooq.com/q/d/l/

## 4. Synthèse pour Investia (étape 1.2)

| Besoin | Source recommandée | Pourquoi |
|---|---|---|
| Prix delayed/intraday `.DE` + `.PA` | Yahoo chart API (déjà en place) | Seule gratuite couvrant les deux places en intraday ; non officielle ⚠️ |
| Historique EOD propre, toutes places Europe | **EODHD free** (clé gratuite) | ToS clair, `.XETRA` + `.PA`, 1 an, 20 appels/jour |
| Delayed 15 min officiel Euronext Paris | **Euronext** (CSV MiFID II / Delayed Data API) | Gratuit par obligation réglementaire, HTTP pur |
| Historique long (25+ ans) Europe | Alpha Vantage free | Global daily, 25 req/jour |
| Recoupement EOD (2ᵉ source) | marketstack free | 100 req/mois, EOD 1 an |
| Normalisation ISIN → ticker `.DE`/`.PA` | OpenFIGI | Gratuit, mapping uniquement |
| FX | Frankfurter (déjà en place) | ECB, gratuit sans clé |
| XETRA temps réel/delayed officiel | **rien en gratuit** | Combo Yahoo `.DE` + EODHD `.XETRA` ; AWS PDS déprécié |

⚠️ Points d'attention : EODHD free = 1 an d'historique et 20 appels/jour (un 404 compte comme un appel) → réserver aux rechargements d'historique, avec cache Redis (déjà en place). Alpha Vantage = 25 req/jour. marketstack = 100 req/mois. Euronext CSV = post-trade, delay 15 min, fichiers gardés ≥ 24 h seulement → à télécharger régulièrement si on veut construire un historique.
