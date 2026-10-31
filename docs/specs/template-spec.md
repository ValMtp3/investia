# Template de spec — à copier pour chaque fonctionnalité

> Règle : **une spec écrite et validée avant d'écrire une seule ligne de code**. 10 à 30 lignes suffisent. Si un critère n'est pas concret et copiable-collable, la spec est trop floue.
>
> Nommage : `docs/specs/<etape>-<feature>.md` (ex. `1-get-quote.md`).

---

# Spec — <nom de la fonctionnalité>

*Écrite le : <date> | Étape roadmap : <n°> | Statut : brouillon / validée / terminée*

## Objectif

Une phrase : ce que fait la fonctionnalité, pour l'utilisateur (toi).

## Pourquoi

Deux phrases max : le problème que ça résout, lié à une décision de `docs/09-decisions.md` si pertinent.

## Contraintes

- Stack imposée (ex. : FastAPI async, pas de synchrone).
- Budget / performance (ex. : réponse < 2 s, coût LLM < 0,01 € par exécution).
- Sécurité (ex. : aucune clé en dur, entrées validées par Pydantic).
- Ce qui existe déjà et ne doit pas casser.

## Critères d'acceptation

Liste à cocher, chacun **concret et vérifiable** (commande, test, comportement observable) :

- [ ] `uv run pytest tests/test_<feature>.py` passe.
- [ ] <comportement observable précis, ex. : appeler `GET /quote?symbol=BTC` renvoie le prix avec sa source et son horodatage>.
- [ ] <cas d'erreur précis, ex. : symbole inconnu → erreur 404 avec message clair>.

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `backend/...` | création / modification de quoi |
| `backend/tests/...` | tests ajoutés |

## Comment vérifier

Les commandes exactes à lancer, dans l'ordre, et le résultat attendu.

```bash
uv run pytest -q
```

## Hors périmètre

Ce que cette spec ne fait **pas** (pour éviter que le code grossisse sans prévenir).
