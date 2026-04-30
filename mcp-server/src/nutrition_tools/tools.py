from datetime import date, timedelta

from .calculator import calculate_targets
from .db import get_conn


def search_food(query: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, calories, protein, carbs, fat,
                       ts_rank(to_tsvector('portuguese', name),
                               plainto_tsquery('portuguese', %s)) AS rank
                FROM taco_foods
                WHERE to_tsvector('portuguese', name) @@ plainto_tsquery('portuguese', %s)
                ORDER BY rank DESC
                LIMIT 5
                """,
                (query, query),
            )
            rows = cur.fetchall()

            if not rows:
                cur.execute(
                    """
                    SELECT id, name, calories, protein, carbs, fat
                    FROM taco_foods
                    WHERE name ILIKE %s
                    LIMIT 5
                    """,
                    (f"%{query}%",),
                )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "calories_per_100g": float(row[2]) if row[2] is not None else 0.0,
                "protein_per_100g": float(row[3]) if row[3] is not None else 0.0,
                "carbs_per_100g": float(row[4]) if row[4] is not None else 0.0,
                "fat_per_100g": float(row[5]) if row[5] is not None else 0.0,
            }
            for row in rows
        ]


def save_user_profile(
    phone: str,
    weight_kg: float,
    height_cm: int,
    age: int,
    sex: str,
    goal: str,
) -> dict:
    if not (20 <= weight_kg <= 300):
        raise ValueError("weight_kg must be between 20 and 300")
    if not (100 <= height_cm <= 250):
        raise ValueError("height_cm must be between 100 and 250")
    if not (10 <= age <= 120):
        raise ValueError("age must be between 10 and 120")
    if sex not in ("M", "F"):
        raise ValueError("sex must be 'M' or 'F'")
    if goal not in ("lose", "maintain", "gain"):
        raise ValueError("goal must be 'lose', 'maintain', or 'gain'")

    targets = calculate_targets(weight_kg, height_cm, age, sex, goal)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    phone_number, weight_kg, height_cm, age, sex, goal,
                    target_calories, target_protein, target_carbs, target_fat
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    weight_kg       = EXCLUDED.weight_kg,
                    height_cm       = EXCLUDED.height_cm,
                    age             = EXCLUDED.age,
                    sex             = EXCLUDED.sex,
                    goal            = EXCLUDED.goal,
                    target_calories = EXCLUDED.target_calories,
                    target_protein  = EXCLUDED.target_protein,
                    target_carbs    = EXCLUDED.target_carbs,
                    target_fat      = EXCLUDED.target_fat
                RETURNING phone_number, weight_kg, height_cm, age, sex, goal,
                          target_calories, target_protein, target_carbs, target_fat
                """,
                (
                    phone,
                    weight_kg,
                    height_cm,
                    age,
                    sex,
                    goal,
                    targets["target_calories"],
                    targets["target_protein"],
                    targets["target_carbs"],
                    targets["target_fat"],
                ),
            )
            row = cur.fetchone()
        return {
            "phone_number": row[0],
            "weight_kg": float(row[1]),
            "height_cm": row[2],
            "age": row[3],
            "sex": row[4],
            "goal": row[5],
            "target_calories": float(row[6]),
            "target_protein": float(row[7]),
            "target_carbs": float(row[8]),
            "target_fat": float(row[9]),
        }


def get_user_profile(phone: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT phone_number, weight_kg, height_cm, age, sex, goal,
                       target_calories, target_protein, target_carbs, target_fat
                FROM users
                WHERE phone_number = %s
                """,
                (phone,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "phone_number": row[0],
        "weight_kg": float(row[1]) if row[1] is not None else None,
        "height_cm": row[2],
        "age": row[3],
        "sex": row[4],
        "goal": row[5],
        "target_calories": float(row[6]) if row[6] is not None else None,
        "target_protein": float(row[7]) if row[7] is not None else None,
        "target_carbs": float(row[8]) if row[8] is not None else None,
        "target_fat": float(row[9]) if row[9] is not None else None,
    }


def save_meal(
    phone: str,
    food_name: str,
    taco_food_id: int,
    quantity_g: float,
) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT calories, protein, carbs, fat FROM taco_foods WHERE id = %s",
                (taco_food_id,),
            )
            food = cur.fetchone()
            if food is None:
                raise ValueError(f"Food with id {taco_food_id} not found")

            factor = quantity_g / 100.0
            calories = round(float(food[0]) * factor, 2)
            protein = round(float(food[1]) * factor, 2)
            carbs = round(float(food[2]) * factor, 2)
            fat = round(float(food[3]) * factor, 2)

            cur.execute(
                """
                INSERT INTO meal_logs
                    (phone_number, food_name, taco_food_id, quantity_g,
                     calories, protein, carbs, fat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, food_name, quantity_g, calories, protein, carbs, fat, logged_at
                """,
                (phone, food_name, taco_food_id, quantity_g, calories, protein, carbs, fat),
            )
            row = cur.fetchone()

        return {
            "id": row[0],
            "food_name": row[1],
            "quantity_g": float(row[2]),
            "calories": float(row[3]),
            "protein": float(row[4]),
            "carbs": float(row[5]),
            "fat": float(row[6]),
            "logged_at": row[7].isoformat(),
        }


def get_daily_summary(phone: str, date_str: str | None = None) -> dict:
    target_date = date.fromisoformat(date_str) if date_str else date.today()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT target_calories, target_protein, target_carbs, target_fat
                FROM users
                WHERE phone_number = %s
                """,
                (phone,),
            )
            user = cur.fetchone()
            if user is None:
                raise ValueError("User not found")

            targets = {
                "calories": float(user[0]) if user[0] is not None else 0.0,
                "protein": float(user[1]) if user[1] is not None else 0.0,
                "carbs": float(user[2]) if user[2] is not None else 0.0,
                "fat": float(user[3]) if user[3] is not None else 0.0,
            }

            cur.execute(
                """
                SELECT COALESCE(SUM(calories), 0),
                       COALESCE(SUM(protein), 0),
                       COALESCE(SUM(carbs), 0),
                       COALESCE(SUM(fat), 0)
                FROM meal_logs
                WHERE phone_number = %s
                  AND logged_at::date = %s
                """,
                (phone, target_date),
            )
            totals_row = cur.fetchone()

    totals = {
        "calories": float(totals_row[0]),
        "protein": float(totals_row[1]),
        "carbs": float(totals_row[2]),
        "fat": float(totals_row[3]),
    }

    def pct(consumed: float, target: float) -> float:
        return round(consumed / target * 100, 1) if target > 0 else 0.0

    return {
        "date": target_date.isoformat(),
        "consumed": totals,
        "targets": targets,
        "percentages": {
            "calories": pct(totals["calories"], targets["calories"]),
            "protein": pct(totals["protein"], targets["protein"]),
            "carbs": pct(totals["carbs"], targets["carbs"]),
            "fat": pct(totals["fat"], targets["fat"]),
        },
    }


def get_weekly_history(phone: str) -> list[dict]:
    today = date.today()
    return [
        get_daily_summary(phone, (today - timedelta(days=i)).isoformat())
        for i in range(6, -1, -1)
    ]
