"""Régression nginx du dashboard : EDGE_SECRET (64 hexa en prod) = clé du `map`.

Sans `map_hash_bucket_size` suffisant, nginx refuse de démarrer :
« could not build map_hash, you should increase map_hash_bucket_size: 64 ».
Vu en prod le 07/11/2026 (en local EDGE_SECRET est vide, le bug était invisible).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "dashboard" / "nginx.conf"

# Marge conservative : nginx stocke la clé + des métadonnées dans chaque bucket.
BUCKET_OVERHEAD = 16


def render(conf: str, edge_secret: str) -> str:
    """Simule l'envsubst de l'image nginx (filtre ^EDGE_)."""
    return conf.replace("${EDGE_SECRET}", edge_secret)


def test_map_hash_bucket_fits_edge_secret_key():
    conf = NGINX_CONF.read_text(encoding="utf-8")
    for secret in ("", "a" * 64):  # local (vide) et prod (64 hexa)
        rendered = render(conf, secret)
        map_block = re.search(r"map\s+\$\w+\s+\$\w+\s*\{(.*?)\}", rendered, re.S)
        assert map_block, "bloc map introuvable dans dashboard/nginx.conf"
        keys = re.findall(r'"([^"]*)"\s+\d+\s*;', map_block.group(1))
        assert len(keys) == 1, f"une seule clé de map attendue, trouvé {keys}"
        bucket = re.search(r"map_hash_bucket_size\s+(\d+)\s*;", rendered)
        assert bucket, (
            "map_hash_bucket_size manquant : nginx refuserait de démarrer "
            "avec une clé de 64 caractères (could not build map_hash)"
        )
        longest = max(len(k) for k in keys)
        assert int(bucket.group(1)) >= longest + BUCKET_OVERHEAD, (
            f"map_hash_bucket_size={bucket.group(1)} trop juste pour une clé "
            f"de {longest} caractères"
        )
