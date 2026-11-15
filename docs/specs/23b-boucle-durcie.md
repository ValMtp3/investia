# Spec 23b — Boucle durcie (SSRF pinning, guard ONNX pinné, canary tokens)

> Chantier 23b, issu de la veille OSS du 15/11/2026 (`docs/veille-oss-2026-11-15.md`, D94).
> Constats à date (vérifiés dans le code le 15/11) :
> - **13b déjà en place** : `guardrails/injection.py` = `RegexInjectionScanner` (toujours actif)
>   + `OnnxInjectionScanner` optionnel (`INJECTION_GUARD_MODEL_PATH`, imports lazy, repli regex,
>   zéro réseau) + `wrap_untrusted` (spotlighting) ; appliqué aux sorties d'outils externes dans
>   la boucle (`injection_policy="block"`, métrique `injections_blocked`).
> - **13d déjà en place** : `payload_hash_for` + hash lié à la décision + **re-vérification du hash
>   juste avant l'exécution** de `simulate_order` (anti replan-after-yes, `loop.py`).
> - **17g partiel** : `guardrails/ssrf.py` valide schéma/userinfo/IP littérale/résolution DNS
>   (toutes les IP doivent être globales) + redirects re-vérifiés un par un dans `tools/pdf.py` —
>   mais **pas de pinning de l'IP à la connexion** (DNS rebinding documenté « hors périmètre 17g »).
>
> => Le delta réel de 23b : fermer le DNS rebinding, pin le modèle ONNX recommandé, ajouter des
> canary tokens maison.

## Objectif

Trois briques, TDD, zéro régression (comportement par défaut inchangé si non configuré) :

### 1. Pinning IP à la connexion (anti DNS rebinding) — ferme la piste notée en 17g

- Nouveau `guardrails/egress.py` : `pinned_async_client(timeout=...) -> httpx.AsyncClient` avec un
  transport custom qui, **à chaque requête** : valide l'URL (`assert_public_http_url`), résout le
  host, re-valide **toutes** les IP, puis ouvre la connexion TCP vers l'IP validée en préservant
  `Host` + SNI du host d'origine (certificat vérifié sur le host, pas sur l'IP).
- Appliqué à `tools/pdf.py` (`ReadPdfTool._download`, URL fournie par l'utilisateur/le modèle) à la
  place du `httpx.AsyncClient` nu. Les redirects continuent d'être suivis manuellement (max 3) avec
  re-validation + re-pinning à chaque saut.
- Les connecteurs marché (hosts fixés en config) ne prennent pas d'URL utilisateur → hors périmètre.
- Tests : transport mocké (aucun réseau) — pinning correct (connexion vers l'IP validée, Host/SNI
  d'origine), rebinding bloqué (2ᵉ résolution privée → `SsrfBlockedError`), redirect
  public→privé bloqué au pinning. `test_ssrf.py`/`test_tools_pdf.py` existants doivent rester verts.

### 2. Guard ONNX pinné — modèle recommandé documenté + test du chemin actif

- Le code 13b existe ; il manque le **pin du modèle** : `Horizon-Labs/prompt-injection-guard-small`
  (mmBERT 140 M, ONNX, Apache-2.0, multilingue, maj 09/11/2026, entraîné sur Nemotron indirect-injection
  + llmail) → documenté dans `.env.example` (`INJECTION_GUARD_MODEL_PATH=/opt/models/prompt-injection-guard-small.onnx`)
  + étape de téléchargement (owner, VPS) dans `docs/verifs-live-vps-2026-11-15.md`.
- Test : session ONNX factice (stub `InferenceSession`/tokenizer) → verdicts blocked/suspicious/clean
  selon les logits ; le fallback regex reste couvert par les tests existants.
- Zéro dépendance ajoutée : `onnxruntime`/`transformers` restent des imports lazy optionnels
  (déjà le cas en 13b) — le modèle est un fichier local, pas une dépendance.

### 3. Canary tokens maison (détection d'exfiltration/injection par le contenu externe)

- Nouveau `guardrails/canary.py` : `CanaryToken` (ex. `CANARY-<32 hex>` aléatoire **par run**),
  injecté dans le délimiteur de contenu externe (`wrap_untrusted(..., canary=...)`), puis recherché :
  - dans les **arguments de chaque tool_call** suivant ;
  - dans la **réponse finale**.
- Hit → verdict `blocked` + event/step `canary_hit` (run_id, turn, où) + incrément d'une métrique
  d'eval `canary_hit`. Faux positifs : le canary n'apparaît que dans le contenu wrappé, jamais affiché
  à l'utilisateur tel quel.
- Câblage dans `loop.py` à côté du scan d'injection 13b (même `injection_policy`).
- Tests : génération unique par run, injection dans le wrapper, détection dans args + réponse finale,
  aucun hit sur texte propre.

## Tests (TDD)

- `test_egress.py` (nouveau) : pinning, rebinding, redirect privé, client par défaut non pinné.
- `test_injection.py` : ajout test session ONNX stubée (3 verdicts).
- `test_canary.py` (nouveau) + test d'intégration boucle : sortie d'outil externe contenant le canary
  → tool_call suivant avec le canary dans ses arguments → bloqué + step `canary_hit`.
- `test_tools_pdf.py` / `test_ssrf.py` existants : zéro régression.

## Fichiers touchés

- `backend/src/investia/guardrails/egress.py` (nouveau), `guardrails/canary.py` (nouveau),
  `guardrails/injection.py` (wrap_untrusted + canary), `tools/pdf.py` (client pinné),
  `agent/loop.py` (câblage canary)
- `backend/tests/test_egress.py`, `test_canary.py` (nouveaux), `test_injection.py`, `test_tools_pdf.py`
- `.env.example`, `docs/STATUS.md`, `docs/09-decisions.md` (D96), `docs/verifs-live-vps-2026-11-15.md`

## Critères d'acceptation

- Suite non-integration verte, ruff/format/ty propres, CI verte.
- `read_pdf` ne se connecte jamais à une IP non validée au moment du connect (test transport mocké).
- Canary hit → blocage + trace, testé en boucle.
- Aucune dépendance ajoutée (onnxruntime/transformers restent optionnels, modèle = fichier local).

## Hors périmètre

- Cedar/OPA pour la policy HITL (évaluation séparée, 13d couvre déjà le hash).
- Pinning des connecteurs marché (hosts fixés).
- Remplacement du scanner regex par un autre modèle.
- Rotation de clés / procedures owner (checklist VPS déjà en place).
