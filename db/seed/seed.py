import csv
import os
import time

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def wait_for_db(max_retries: int = 15) -> None:
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            print("Database is ready.")
            return
        except psycopg2.OperationalError:
            print(f"Waiting for database... ({i + 1}/{max_retries})")
            time.sleep(2)
    raise RuntimeError("Could not connect to the database after multiple retries.")


def run_migration(conn: psycopg2.extensions.connection) -> None:
    migration_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_init.sql")
    with open(migration_path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("Migration applied.")


def seed_taco(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM taco_foods")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"TACO already has {count} rows, skipping seed.")
            return

    csv_path = os.path.join(os.path.dirname(__file__), "taco.csv")
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO taco_foods (name, calories, protein, carbs, fat)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    row["name"],
                    float(row["calories"]) if row["calories"] else None,
                    float(row["protein"]) if row["protein"] else None,
                    float(row["carbs"]) if row["carbs"] else None,
                    float(row["fat"]) if row["fat"] else None,
                ),
            )
    conn.commit()
    print(f"Seeded {len(rows)} TACO foods.")


def main() -> None:
    wait_for_db()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        run_migration(conn)
        seed_taco(conn)
    finally:
        conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
