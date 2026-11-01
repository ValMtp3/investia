"""Tests d'intégration des tables eval (migration 0003) + enregistrement de scores."""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from investia.db import get_session

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL non défini")
def test_alembic_upgrade_head_creates_eval_tables(monkeypatch):
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    import investia.db as db_module

    db_module._engine = None
    db_module._session_factory = None
    import asyncio

    async def check():
        async with get_session()() as session:
            count = await session.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name IN ('eval_runs', 'eval_results')"
                )
            )
            assert count.scalar() == 2

    asyncio.run(check())
    db_module._engine = None
    db_module._session_factory = None
