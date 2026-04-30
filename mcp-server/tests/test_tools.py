from datetime import date, timedelta

import psycopg2
import pytest

from nutrition_tools import tools


PHONE = "5511900000001"


def test_get_user_profile_returns_none_when_missing():
    assert tools.get_user_profile(PHONE) is None


def test_save_and_get_user_profile_round_trip():
    saved = tools.save_user_profile(PHONE, 80, 180, 30, "M", "maintain")
    fetched = tools.get_user_profile(PHONE)
    assert fetched == saved
    assert saved["target_calories"] == 2136


def test_save_user_profile_validates_ranges():
    with pytest.raises(ValueError):
        tools.save_user_profile(PHONE, 10, 180, 30, "M", "maintain")  # weight too low
    with pytest.raises(ValueError):
        tools.save_user_profile(PHONE, 80, 80, 30, "M", "maintain")   # height too low
    with pytest.raises(ValueError):
        tools.save_user_profile(PHONE, 80, 180, 30, "X", "maintain")  # bad sex
    with pytest.raises(ValueError):
        tools.save_user_profile(PHONE, 80, 180, 30, "M", "bulk")      # bad goal


def test_save_meals_inserts_proportionally():
    tools.save_user_profile(PHONE, 80, 180, 30, "M", "maintain")
    saved = tools.save_meals(
        PHONE,
        [
            {"food_name": "Frango grelhado", "taco_food_id": 1, "quantity_g": 200},
            {"food_name": "Arroz branco cozido", "taco_food_id": 2, "quantity_g": 150},
        ],
    )
    assert len(saved) == 2
    # 200g of 219 kcal/100g = 438
    assert saved[0]["calories"] == 438.0
    # 150g of 128 kcal/100g = 192
    assert saved[1]["calories"] == 192.0


def test_save_meals_atomic_when_one_item_invalid(db_url):
    tools.save_user_profile(PHONE, 80, 180, 30, "M", "maintain")
    with pytest.raises(ValueError):
        tools.save_meals(
            PHONE,
            [
                {"food_name": "Frango grelhado", "taco_food_id": 1, "quantity_g": 200},
                {"food_name": "Bogus", "taco_food_id": 9999, "quantity_g": 100},
            ],
        )
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM meal_logs WHERE phone_number = %s", (PHONE,))
        assert cur.fetchone()[0] == 0
    conn.close()


def test_get_daily_summary_returns_none_without_profile():
    assert tools.get_daily_summary(PHONE) is None


def test_get_daily_summary_aggregates_today():
    tools.save_user_profile(PHONE, 80, 180, 30, "M", "maintain")
    tools.save_meals(
        PHONE,
        [
            {"food_name": "Frango grelhado", "taco_food_id": 1, "quantity_g": 200},
            {"food_name": "Arroz branco cozido", "taco_food_id": 2, "quantity_g": 150},
        ],
    )
    summary = tools.get_daily_summary(PHONE)
    assert summary["consumed"]["calories"] == 438.0 + 192.0
    assert summary["targets"]["calories"] == 2136
    assert summary["percentages"]["calories"] == round((630 / 2136) * 100, 1)


def test_get_weekly_history_returns_seven_days_or_none():
    assert tools.get_weekly_history(PHONE) is None
    tools.save_user_profile(PHONE, 80, 180, 30, "M", "maintain")
    history = tools.get_weekly_history(PHONE)
    assert len(history) == 7
    today = date.today()
    expected_dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    assert [day["date"] for day in history] == expected_dates


def test_search_food_finds_by_portuguese_fts():
    results = tools.search_food("frango")
    names = [r["name"] for r in results]
    assert any("Frango" in n for n in names)
