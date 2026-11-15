"""Tests 23a — lockfiles : versions minimales pinnées contre les CVE/backdoors 2026.

Garde-fous de régression (stdlib uniquement) : si un bump de dépendance fait
rentrer une version vulnérable, ces tests cassent en CI.
"""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UV_LOCK = ROOT / "backend" / "uv.lock"
PKG_LOCK = ROOT / "dashboard" / "package-lock.json"


def _uv_version(name: str) -> str:
    data = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    for pkg in data["package"]:
        if pkg["name"] == name:
            return str(pkg["version"])
    raise AssertionError(f"{name} absent de uv.lock")


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def test_certifi_au_dessus_du_fix_emudhra():
    """CVE-2026-115557 (CA eMudhra, oct 2026) : certifi ≥ 2026.10.19."""
    assert _tuple(_uv_version("certifi")) >= (2026, 10, 19)


def test_fastmcp_et_mcp_patches_cve_2026():
    """CVE MCP 2026 (redirects, OAuth issuer, $ref) : fastmcp ≥ 4.2.0,
    mcp ≥ 2.3.0."""
    assert _tuple(_uv_version("fastmcp")) >= (4, 2, 0)
    assert _tuple(_uv_version("mcp")) >= (2, 3, 0)


def test_react_lockfile_patche_cve_2026_126187():
    """CVE-2026-126187 (RCE RSC, fix 19.3.1) : react/react-dom ≥ 19.3.1."""
    packages = json.loads(PKG_LOCK.read_text(encoding="utf-8"))["packages"]
    for name in ("node_modules/react", "node_modules/react-dom"):
        assert _tuple(packages[name]["version"]) >= (19, 3, 1), name
