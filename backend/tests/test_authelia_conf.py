"""Régression config Authelia : D63 (07/11/2026) — mot de passe seul, plus de 2FA TOTP.

La 2FA a été retirée par le propriétaire car l'enregistrement TOTP exigeait un
e-mail que le VPS n'envoie pas (risque assumé, voir docs/09-decisions.md D63).
Ce test épingle la policy `one_factor` pour que la config du repo reflète le VPS.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF = REPO_ROOT / "deploy" / "authelia" / "configuration.yml"


def test_authelia_policy_is_one_factor_not_two_factor():
    conf = CONF.read_text(encoding="utf-8")
    policies = re.findall(r"policy:\s*'(\w+)'", conf)
    assert "two_factor" not in policies, (
        "D63 : la 2FA TOTP est retirée (risque assumé) — ne pas remettre "
        "two_factor sans nouvelle décision documentée"
    )
    assert "one_factor" in policies
    assert "default_policy: 'deny'" in conf, "tout reste fermé par défaut"


def test_no_secret_in_authelia_conf():
    """Dépôt public (D42) : aucun secret en dur dans la config Authelia."""
    conf = CONF.read_text(encoding="utf-8")
    for forbidden in ("password:", "secret:", "key:", "hash:"):
        # les champs attendus (noms de variables) ne doivent pas contenir de valeur
        for line in conf.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not re.match(rf"^\s*{forbidden}\s*\S", stripped), (
                f"valeur en dur suspecte dans configuration.yml : {stripped!r}"
            )
