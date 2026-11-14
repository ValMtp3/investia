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
