"""Test fixtures.

Integration tests need a real Postgres because the tools rely on
Portuguese full-text search and `ON CONFLICT` upserts that no in-memory
fake reproduces faithfully. Set TEST_DATABASE_URL to a disposable
database before running pytest:

    export TEST_DATABASE_URL=postgresql://nutrition:test@localhost:5432/nutrition_test
    pip install -e .[test]
    pytest

The session-scoped fixture wipes and re-applies the migration, then
seeds two TACO foods used by the meal tests. Each test runs against a
truncated `users` and `meal_logs` so order doesn't matter.
"""

import os
from pathlib import Path

import psycopg2
import pytest


def _migration_sql() -> str:
    here = Path(__file__).resolve().parent
    migration = here.parent.parent / "db" / "migrations" / "001_init.sql"
    return migration.read_text()


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set — skipping integration tests")
    return url


@pytest.fixture(scope="session", autouse=True)
def schema_and_pool(db_url):
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS meal_logs CASCADE")
        cur.execute("DROP TABLE IF EXISTS users CASCADE")
        cur.execute("DROP TABLE IF EXISTS taco_foods CASCADE")
        cur.execute(_migration_sql())
        cur.execute(
            """
            INSERT INTO taco_foods (id, name, calories, protein, carbs, fat) VALUES
                (1, 'Frango grelhado', 219, 32.0, 0.0, 9.5),
                (2, 'Arroz branco cozido', 128, 2.5, 28.1, 0.2),
                (3, 'Feijão preto cozido', 77, 4.5, 14.0, 0.5)
            """
        )
    conn.commit()
    conn.close()

    os.environ["DATABASE_URL"] = db_url
    from nutrition_tools import db

    db.init_pool()
    yield


@pytest.fixture(autouse=True)
def truncate_per_test(db_url):
    yield
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE users, meal_logs CASCADE")
    conn.commit()
    conn.close()
