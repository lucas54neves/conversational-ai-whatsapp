"""Root pytest harness.

Integration tests need a real Postgres because the MCP tools rely on
Portuguese full-text search and `ON CONFLICT` upserts that no in-memory
fake reproduces faithfully. A `postgres:16-alpine` container is started
once per session via `testcontainers`, but only when the collected
tests include items under `tests/integration/`. Pure-unit runs
(`pytest tests/unit/`) skip the Docker startup entirely.
"""

import importlib.util
import os
from pathlib import Path

import psycopg2
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_SQL = REPO_ROOT / "db" / "migrations" / "001_init.sql"
SEED_SCRIPT = REPO_ROOT / "db" / "seed" / "seed.py"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/integration/" in item.nodeid.replace(os.sep, "/"):
            item.add_marker(pytest.mark.integration)


def _has_integration_items(session) -> bool:
    return any(
        "tests/integration/" in item.nodeid.replace(os.sep, "/")
        for item in session.items
    )


@pytest.fixture(scope="session")
def db_url(request) -> str:
    if not _has_integration_items(request.session):
        pytest.skip("no integration tests collected")

    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    request.addfinalizer(container.stop)

    url = container.get_connection_url()
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)

    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        cur.execute(MIGRATION_SQL.read_text())
    conn.commit()
    conn.close()

    os.environ["DATABASE_URL"] = url
    from nutrition_tools import db

    db.init_pool()
    return url


@pytest.fixture(scope="session")
def seed_module(db_url):
    spec = importlib.util.spec_from_file_location("seed_loader", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
