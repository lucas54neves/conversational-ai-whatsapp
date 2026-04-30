"""Per-test fixtures for integration tests.

`taco_minimal` and `_truncate_logs` run on every test in this directory
so each one starts with the same three reference foods and an empty
log/user state. The minimal seed is re-applied per test (not session-
scoped) because `test_seed.py` swaps `taco_foods` for the full TACO
dataset; running per-test guarantees the next test sees the minimal
subset regardless of order.
"""

import psycopg2
import pytest

_TACO_MINIMAL_ROWS = [
    (1, "Frango grelhado", 219, 32.0, 0.0, 9.5),
    (2, "Arroz branco cozido", 128, 2.5, 28.1, 0.2),
    (3, "Feijão preto cozido", 77, 4.5, 14.0, 0.5),
]


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


@pytest.fixture(autouse=True)
def taco_minimal(db_url):
    _seed_taco_minimal(db_url)


@pytest.fixture(autouse=True)
def _truncate_logs(db_url):
    yield
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE users, meal_logs CASCADE")
    conn.commit()
    conn.close()
