# Mode live — guide des clés API (étape 8)

Toutes les clés étaient fictives en local. En prod (VPS), elles vont dans `~/investia/.env` **uniquement** — jamais dans le repo (D42), jamais affichées (pas de `echo`, pas de `cat .env` dans un log).

## Clés à créer (gratuites) et où

| Variable `.env` | Fournisseur | Créer sur | Quoi mettre |
|---|---|---|---|
| `OPENROUTER_API_KEY` | OpenRouter | openrouter.ai/keys | clé `sk-or-...` (crédits à acheter, budget 10-20 €/mois D22) |
| `MISTRAL_API_KEY` | Mistral | console.mistral.ai | clé API Mistral (appels directs Mistral Large 4) |
| `TYPESAFE_API_KEY` | TypeSafe (Jev) | portail TypeSafe | clé pour le modèle de décision |
| `FINNHUB_API_KEY` | Finnhub | finnhub.io | gratuit, US temps réel + news |
| `EODHD_API_KEY` | EODHD | eodhd.com | gratuit, historique Europe |
| `TWELVEDATA_API_KEY` | Twelve Data | twelvedata.com | gratuit (crédits/jour limités) |
| `MASSIVE_API_KEY` | Massive | massive.com | gratuit |
| `COINGECKO_DEMO_API_KEY` | CoinGecko | coingecko.com/demo | gratuit |

Stooq a été retiré (challenge JS depuis 2026, D36/Q9). Frankfurter (taux) n'a pas besoin de clé.

## Procédure sur le VPS (jamais de secret affiché)

```bash
cd ~/investia
nano .env          # remplir les clés ci-dessus, sauvegarder (Ctrl+O, Entrée, Ctrl+X)
# ne JAMAIS faire : cat .env, echo $KEY, ou copier-coller une valeur dans le chat
bash ~/investia/deploy/update.sh    # rebuild + restart (le backend relit .env au démarrage)
```

## Vérifier que le live marche

```bash
# 1. Live check LLM (1 appel minimal, protégé par le jeton admin — D51) :
curl -s -H "X-Admin-Token: $APP_SECRET_KEY" https://investia.valentin-fiess.fr/api/live/llm
# attendu : {"ok":true,"model":"gpt-6-luna","cost_cents":...,"duration_ms":...}
# si clé manquante : {"ok":false,"error":"clé LLM manquante ..."}

# 2. L'agent répond vraiment dans le chat :
# ouvrir https://investia.valentin-fiess.fr/agent, poser « Quel est le prix de AAPL ? »

# 3. Evals réelles de la comparaison 6.3 (budget 2 € bloqué en code, D62) — en local avec les vraies clés dans .env :
cd ~/investia/comparisons && uv run python run_evals.py --live --budget-eur 2
# → results-live.json (s'arrête tout seul au dépassement du budget)
```

## Si une clé manque

- Le live check renvoie `ok:false` avec le nom de la clé manquante.
- Les sources marché sans clé sont sautées automatiquement par la cascade (D46) : le prix vient de la source suivante.
- Aucun secret n'est jamais loggué : httpx est remonté en WARNING (les clés en paramètre d'URL ne fuient pas dans les logs).
