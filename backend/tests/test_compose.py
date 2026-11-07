"""Tests de config Docker Compose — parse les YAML, n'exécute pas Docker."""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"

SERVICES = {"postgres", "redis", "backend", "litellm"}


def load_compose(name: str) -> dict:
    return yaml.safe_load((DEPLOY_DIR / name).read_text(encoding="utf-8"))


def test_all_services_present_in_base_compose():
    compose = load_compose("docker-compose.yml")
    assert SERVICES <= set(compose["services"].keys())


def test_base_compose_publishes_no_ports():
    compose = load_compose("docker-compose.yml")
    for service_name, service in compose["services"].items():
        assert "ports" not in service, (
            f"docker-compose.yml:{service_name} publie des ports"
        )


def test_prod_compose_publishes_only_loopback_ports_on_edge_services():
    # D54 : NPM est en network_mode: host sur le VPS, il atteint la pile en localhost.
    # Seuls dashboard/authelia peuvent publier un port, lié à 127.0.0.1 uniquement.
    compose = load_compose("docker-compose.prod.yml")
    for service_name, service in compose["services"].items():
        for port in service.get("ports", []):
            assert service_name in {"dashboard", "authelia"}, (
                f"docker-compose.prod.yml:{service_name} publie un port"
            )
            assert str(port).startswith("127.0.0.1:"), (
                f"{service_name}: {port} n'est pas lié à 127.0.0.1"
            )


def test_prod_edge_services_expose_a_loopback_port_for_npm():
    # Sans port loopback, NPM (host) ne pourrait jamais atteindre la pile (D54).
    compose = load_compose("docker-compose.prod.yml")
    for name in ("dashboard", "authelia"):
        ports = compose["services"][name].get("ports", [])
        assert ports, f"docker-compose.prod.yml:{name} n'expose aucun port loopback"
        assert all(str(p).startswith("127.0.0.1:") for p in ports), name


def test_prod_compose_uses_no_external_network():
    # D54 : plus de réseau Docker externe (NPM est en network_mode: host).
    compose = load_compose("docker-compose.prod.yml")
    for net_name, net in compose.get("networks", {}).items():
        assert not net.get("external"), f"réseau externe interdit en prod : {net_name}"


def test_local_override_binds_every_port_to_localhost():
    override = load_compose("docker-compose.override.yml")
    for service_name, service in override["services"].items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{service_name}: {port}"


def test_postgres_image_is_pgvector_pg17():
    compose = load_compose("docker-compose.yml")
    assert compose["services"]["postgres"]["image"] == "pgvector/pgvector:pg17"


def test_redis_image_is_redis_8():
    compose = load_compose("docker-compose.yml")
    assert compose["services"]["redis"]["image"] == "redis:8"


def test_litellm_image_is_pinned_to_a_version_not_latest():
    compose = load_compose("docker-compose.yml")
    image = compose["services"]["litellm"]["image"]
    assert "latest" not in image
    assert re.match(r"^ghcr\.io/berriai/litellm:v\d+\.\d+\.\d+", image), image


def test_litellm_config_declares_chat_models_and_elephant():
    config = yaml.safe_load(
        (DEPLOY_DIR / "litellm" / "config.yaml").read_text(encoding="utf-8")
    )
    models = {
        m["model_name"]: m["litellm_params"]["model"] for m in config["model_list"]
    }
    assert {"gpt-6-luna", "mistral-large-4", "elephant"} <= set(models)


def test_litellm_providers_are_openrouter_for_gpt_elephant_mistral_direct():
    config = yaml.safe_load(
        (DEPLOY_DIR / "litellm" / "config.yaml").read_text(encoding="utf-8")
    )
    models = {
        m["model_name"]: m["litellm_params"]["model"] for m in config["model_list"]
    }
    assert models["gpt-6-luna"].startswith("openrouter/"), models["gpt-6-luna"]
    assert models["elephant"].startswith("openrouter/"), models["elephant"]
    assert models["mistral-large-4"] == "mistral/mistral-large-4"
