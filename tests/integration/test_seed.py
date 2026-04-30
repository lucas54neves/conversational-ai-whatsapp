"""Integration tests for the TACO seed loader (db/seed/seed.py).

The loader reads a CSV next to the script and inserts every row into
`taco_foods`, with a count-based short-circuit to make re-runs idempotent.
Each test wipes `taco_foods` first because the `taco_minimal` autouse
fixture in conftest.py pre-seeds three reference rows, which would
otherwise trip the loader's "already populated" guard.
"""

import csv
from pathlib import Path

import psycopg2


def _row_count(db_url: str) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM taco_foods")
            return cur.fetchone()[0]
    finally:
        conn.close()


def _wipe_taco(db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE taco_foods CASCADE")
    conn.commit()
    conn.close()


def _csv_data_row_count(seed_module) -> int:
    csv_path = Path(seed_module.__file__).parent / "taco.csv"
    with csv_path.open(newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_seed_inserts_full_taco_dataset(seed_module, db_url):
    _wipe_taco(db_url)
    seed_module.main()
    assert _row_count(db_url) == _csv_data_row_count(seed_module)


def test_seed_is_idempotent(seed_module, db_url):
    _wipe_taco(db_url)
    seed_module.main()
    first = _row_count(db_url)
    seed_module.main()
    assert _row_count(db_url) == first


def test_seed_preserves_known_food(seed_module, db_url):
    _wipe_taco(db_url)
    seed_module.main()
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT calories, protein, carbs, fat FROM taco_foods WHERE name ILIKE %s",
                ("%arroz%branco%cozido%",),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    calories, protein, carbs, fat = row
    assert calories > 0
    assert protein >= 0
    assert carbs >= 0
    assert fat >= 0


def test_seed_skips_when_already_populated(seed_module, db_url):
    _wipe_taco(db_url)
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO taco_foods (id, name, calories, protein, carbs, fat)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (9999, "Synthetic placeholder", 1, 0, 0, 0),
        )
    conn.commit()
    conn.close()

    seed_module.main()

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM taco_foods")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT name FROM taco_foods WHERE id = %s", (9999,))
            assert cur.fetchone()[0] == "Synthetic placeholder"
    finally:
        conn.close()
