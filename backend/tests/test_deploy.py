"""Tests 17h — deploy : les images Docker du docker-compose sont épinglées
(tag de version ou digest, jamais `latest`). Garde-fou supply-chain qui
stabilise aussi les scans CVE du workflow cve-alerts.yml."""

import re
from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.yml"


def _images() -> list[str]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    images = []
    for service in (data.get("services") or {}).values():
        image = service.get("image")
        if image:
            images.append(str(image))
    return images


def test_compose_declare_des_images():
    assert len(_images()) >= 3  # pgvector, redis, litellm


def test_images_epinglees_jamais_latest():
    for image in _images():
        assert ":latest" not in image, f"image non épinglée : {image}"
        # tag explicite (hors latest, déjà testé) ou digest sha256
        has_tag = re.search(r":[A-Za-z0-9][0-9a-zA-Z._-]*$", image)
        assert has_tag or "@sha256:" in image, f"image sans tag ni digest : {image}"


# --- 23a : supply-chain — pins CVE/backdoors 2026 (veille 15/11, D95) ---

CVE_ALERTS = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cve-alerts.yml"
)


def _compose_image(name_part: str) -> str:
    for image in _images():
        if name_part in image:
            return image
    raise AssertionError(f"image {name_part!r} introuvable dans le compose")


def test_image_pgvector_pinee_0_8_7_minimum():
    """23a : CVE-2026-103484 (RCE IVFFlat, pgvector ≤ 0.8.6) — pin ≥ 0.8.7."""
    image = _compose_image("pgvector/pgvector")
    m = re.search(r":(\d+)\.(\d+)\.(\d+)-pg17$", image)
    assert m, f"pgvector non pinné par version exacte : {image}"
    assert tuple(int(x) for x in m.groups()) >= (0, 8, 7)


def test_image_litellm_hors_versions_backdoorees():
    """23a : backdoors litellm 2026 — 1.82.7/1.82.8 (TeamPCP), 1.107.0 (oct 2026)
    interdites ; backport sécu #51254 = v1.109.1 minimum."""
    image = _compose_image("berriai/litellm")
    m = re.search(r":v(\d+)\.(\d+)\.(\d+)", image)
    assert m, f"litellm sans version exacte : {image}"
    version = tuple(int(x) for x in m.groups())
    backdoors = {(1, 82, 7), (1, 82, 8), (1, 107, 0)}
    assert version not in backdoors, f"version backdoorée : {image}"
    assert version >= (1, 109, 1), f"litellm < v1.109.1 (backport sécu) : {image}"


def test_workflow_cve_alerts_job_osv_epingle():
    """23a : job OSV/MAL présent, version épinglée, job alerte branché."""
    text = CVE_ALERTS.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    jobs = data["jobs"]
    assert "osv" in jobs, "job 'osv' manquant dans cve-alerts.yml"
    assert re.search(r'OSV_SCANNER_VERSION: "v\d+\.\d+\.\d+"', text), (
        "OSV_SCANNER_VERSION doit être épinglé (jamais latest)"
    )
    needs = jobs["alerte"]["needs"]
    needs_list = needs if isinstance(needs, list) else [needs]
    assert "osv" in needs_list, "le job alerte doit dépendre aussi du job osv"
