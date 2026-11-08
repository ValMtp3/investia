"""TDD étape 11 : rôles PostgreSQL applicatifs sans SUPERUSER (D68, risque D53).

Tests statiques (pas de Docker exécuté) : le script d'init crée deux rôles
applicatifs limités, transfère les bases, révoque CONNECT à PUBLIC ; le compose
passe les mots de passe au service postgres ; .env.example pointe les URLs vers
les rôles app ; le backup garde le compte admin ; le script one-shot VPS existe.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"
INIT_DIR = DEPLOY_DIR / "postgres" / "init"
INIT_SCRIPT = INIT_DIR / "03-create-app-roles.sh"
ONESHOT_SCRIPT = DEPLOY_DIR / "postgres" / "apply-app-roles.sh"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_init_script_exists():
    assert INIT_SCRIPT.exists(), f"script manquant : {INIT_SCRIPT}"


def test_init_creates_two_app_roles_without_admin_privileges():
    sql = read(INIT_SCRIPT)
    assert "investia_app" in sql and "litellm_app" in sql
    # Chaque rôle est créé puis verrouillé explicitement (idempotent).
    for role in ("investia_app", "litellm_app"):
        assert re.search(rf"ALTER ROLE {role} .*NOSUPERUSER", sql), role
    assert "NOCREATEDB" in sql and "NOCREATEROLE" in sql
    # Aucun octroi de SUPERUSER dans le code (hors commentaires/echo/NOSUPERUSER).
    code_lines = [
        line
        for line in sql.splitlines()
        if not line.lstrip().startswith("#") and not line.lstrip().startswith("echo")
    ]
    code = "\n".join(code_lines).replace("NOSUPERUSER", "")
    assert "SUPERUSER" not in code, "SUPERUSER ne doit jamais être accordé"


def test_init_transfers_database_ownership_to_app_roles():
    sql = read(INIT_SCRIPT)
    assert re.search(r"ALTER DATABASE investia OWNER TO investia_app", sql)
    assert re.search(r"ALTER DATABASE litellm OWNER TO litellm_app", sql)
    # Les objets existants (tables des migrations) suivent le nouveau propriétaire.
    # (pas de REASSIGN OWNED : il toucherait les objets partagés, refusé par PostgreSQL)
    code = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("#")
    )
    assert "REASSIGN OWNED" not in code
    assert re.search(r"ALTER SCHEMA public OWNER TO investia_app", sql)
    assert re.search(r"ALTER TABLE %I\.%I OWNER TO investia_app", sql)
    assert re.search(r"ALTER SCHEMA public OWNER TO litellm_app", sql)
    assert re.search(r"ALTER TABLE %I\.%I OWNER TO litellm_app", sql)


def test_init_revokes_public_connect_on_app_databases():
    sql = read(INIT_SCRIPT)
    assert "REVOKE CONNECT ON DATABASE investia FROM PUBLIC" in sql
    assert "REVOKE CONNECT ON DATABASE litellm FROM PUBLIC" in sql
    # La base "postgres" et template1 aussi : un rôle app ne se connecte qu'à sa base.
    assert "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC" in sql
    assert "REVOKE CONNECT ON DATABASE template1 FROM PUBLIC" in sql


def test_init_creates_pgvector_extension_as_admin():
    # CREATE EXTENSION exige un privilège système : fait par l'admin, pas le rôle app.
    sql = read(INIT_SCRIPT)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql


def test_init_is_idempotent_and_updates_passwords():
    sql = read(INIT_SCRIPT)
    assert "WHERE NOT EXISTS" in sql, "CREATE ROLE conditionnel (rejouable)"
    # ALTER ROLE rejoué à chaque passage : le mot de passe suit toujours l'env.
    assert re.search(r"ALTER ROLE investia_app LOGIN PASSWORD", sql)
    assert re.search(r"ALTER ROLE litellm_app LOGIN PASSWORD", sql)


def test_init_skips_cleanly_without_passwords_in_local():
    # Même convention que 02-create-authelia-db.sh : pas de mot de passe = pas de rôle.
    sql = read(INIT_SCRIPT)
    assert re.search(r"\[ -z \"\$\{INVESTIA_APP_DB_PASSWORD:-\}\" \]", sql)
    assert "LITELLM_APP_DB_PASSWORD" in sql


def test_compose_passes_app_passwords_to_postgres_service():
    compose = yaml.safe_load(read(DEPLOY_DIR / "docker-compose.yml"))
    env = compose["services"]["postgres"]["environment"]
    env_text = yaml.safe_dump(env)
    assert "INVESTIA_APP_DB_PASSWORD" in env_text
    assert "LITELLM_APP_DB_PASSWORD" in env_text


def test_env_example_urls_use_app_roles_and_admin_stays_for_backup():
    text = read(REPO_ROOT / ".env.example")
    assert "postgresql+asyncpg://investia_app:" in text, "DATABASE_URL -> investia_app"
    assert "postgresql://litellm_app:" in text, "LITELLM_DATABASE_URL -> litellm_app"
    # Le compte superuser reste documenté comme admin (backup uniquement).
    assert re.search(r"^POSTGRES_USER=investia$", text, re.MULTILINE)
    assert "INVESTIA_APP_DB_PASSWORD=" in text
    assert "LITELLM_APP_DB_PASSWORD=" in text


def test_prod_backup_keeps_admin_account_and_app_services_do_not():
    prod = yaml.safe_load(read(DEPLOY_DIR / "docker-compose.prod.yml"))
    backup_env = prod["services"]["backup"]["environment"]
    assert backup_env["PGUSER"] == "${POSTGRES_USER:-investia}", (
        "le backup garde le compte admin (pg_dump)"
    )
    base = yaml.safe_load(read(DEPLOY_DIR / "docker-compose.yml"))
    for service in ("backend", "litellm"):
        env_text = yaml.safe_dump(base["services"][service].get("environment", {}))
        assert "POSTGRES_PASSWORD" not in env_text, (
            f"{service} ne doit plus recevoir le mot de passe admin"
        )


def test_oneshot_script_exists_and_replays_init_script_in_container():
    assert ONESHOT_SCRIPT.exists(), f"script one-shot manquant : {ONESHOT_SCRIPT}"
    content = read(ONESHOT_SCRIPT)
    assert "03-create-app-roles.sh" in content, "rejoue le script d'init idempotent"
    assert "docker compose" in content and "exec" in content
    assert "INVESTIA_APP_DB_PASSWORD" in content
    assert "LITELLM_APP_DB_PASSWORD" in content
    # Les secrets ne sont jamais affichés (pas de echo des mots de passe).
    assert not re.search(r"echo .*DB_PASSWORD", content)
