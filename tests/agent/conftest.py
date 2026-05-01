"""Per-test fixtures for the agent reasoning tiers.

Agent tests participate in the existing Postgres testcontainer lifecycle
started by `tests/conftest.py`. We reseed the minimal TACO subset and
truncate `users`/`meal_logs` between tests so each scenario starts from
the same baseline, mirroring the integration-tier conventions.
"""

from __future__ import annotations

import os

import psycopg2
import pytest

_TACO_MINIMAL_ROWS = [
    (1, "Frango grelhado", 219, 32.0, 0.0, 9.5),
    (2, "Arroz branco cozido", 128, 2.5, 28.1, 0.2),
    (3, "Feijão preto cozido", 77, 4.5, 14.0, 0.5),
]


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/agent/" in item.nodeid.replace(os.sep, "/"):
            item.add_marker(pytest.mark.integration)


def _seed_taco_minimal(db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE taco_foods CASCADE")
        cur.executemany(
            "INSERT INTO taco_foods (id, name, calories, protein, carbs, fat)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            _TACO_MINIMAL_ROWS,
        )
    conn.commit()
    conn.close()


def _truncate_logs(db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE users, meal_logs CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def agent_db(db_url):
    _seed_taco_minimal(db_url)
    _truncate_logs(db_url)
    yield db_url
    _truncate_logs(db_url)
