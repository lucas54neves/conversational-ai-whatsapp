"""Eval-tier runner that drives `run_agent` against the real Anthropic API.

Each case in `cases.yaml` becomes a parametrized test that records
pass/fail in a session-scoped collector instead of hard-failing, so a
single bad case does not mask the cumulative pass rate. The aggregate
test at the bottom of this file enforces `PASS_RATE_THRESHOLD`.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest
import yaml
from nutrition_tools import tools

from tests.agent.harness import run_agent

PASS_RATE_THRESHOLD = 0.85
CASES_PATH = Path(__file__).parent / "cases.yaml"


def _load_cases() -> list[dict]:
    return yaml.safe_load(CASES_PATH.read_text())


def _seed_user(phone: str) -> None:
    tools.save_user_profile(phone, 70, 175, 30, "M", "maintain")


def _seed_meal(phone: str, food_id: int, quantity_g: float) -> None:
    tools.save_meals(
        phone,
        [
            {
                "food_name": f"taco_{food_id}",
                "taco_food_id": food_id,
                "quantity_g": quantity_g,
            }
        ],
    )


def _query_meal_logs_count(db_url: str, phone: str) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM meal_logs WHERE phone_number = %s",
                (phone,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def _query_kcal_sum(db_url: str, phone: str) -> float:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(calories), 0) FROM meal_logs WHERE phone_number = %s",
                (phone,),
            )
            return float(cur.fetchone()[0])
    finally:
        conn.close()


def _query_users_count(db_url: str) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM users")
            return cur.fetchone()[0]
    finally:
        conn.close()


def _validate_case(case: dict, result, db_url: str) -> None:
    phone = case["phone"]
    called = {c.name for c in result.tool_calls}

    expected = set(case.get("expected_tools_subset") or [])
    missing = expected - called
    assert not missing, f"missing expected tools {missing}; called={called}"

    forbidden = set(case.get("forbidden_tools") or [])
    forbidden_hit = forbidden & called
    assert not forbidden_hit, f"forbidden tools called: {forbidden_hit}"

    expected_db = case.get("expected_db") or {}
    if "meal_logs_count" in expected_db:
        actual = _query_meal_logs_count(db_url, phone)
        assert actual == expected_db["meal_logs_count"], (
            f"meal_logs_count: expected {expected_db['meal_logs_count']}, got {actual}"
        )
    if "kcal_range" in expected_db:
        lo, hi = expected_db["kcal_range"]
        actual = _query_kcal_sum(db_url, phone)
        assert lo <= actual <= hi, f"kcal {actual} not in [{lo}, {hi}]"
    if "users_count" in expected_db:
        actual = _query_users_count(db_url)
        assert actual == expected_db["users_count"], (
            f"users_count: expected {expected_db['users_count']}, got {actual}"
        )

    text = (result.final_text or "").lower()
    for keyword in case.get("expected_assistant_response_contains") or []:
        assert keyword.lower() in text, f"missing keyword {keyword!r} in response"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_eval_case(case, agent_db, real_anthropic_client, eval_results):
    phone = case["phone"]
    if case.get("preseed_user"):
        _seed_user(phone)
    preseed_meal = case.get("preseed_meal")
    if preseed_meal:
        _seed_meal(phone, preseed_meal["food_id"], preseed_meal["quantity_g"])

    try:
        result = run_agent(
            real_anthropic_client,
            case["conversation"],
            user_phone=phone,
            max_turns=case.get("max_turns", 10),
        )
        _validate_case(case, result, agent_db)
    except Exception as exc:
        eval_results["fail"] += 1
        eval_results["failures"].append(f"{case['name']}: {type(exc).__name__}: {exc}")
        print(f"FAIL {case['name']}: {type(exc).__name__}: {exc}")
    else:
        eval_results["pass"] += 1


def test_aggregate_pass_rate(eval_results):
    total = eval_results["pass"] + eval_results["fail"]
    if total == 0:
        pytest.skip("no eval cases recorded")
    rate = eval_results["pass"] / total
    assert rate >= PASS_RATE_THRESHOLD, (
        f"pass rate {rate:.2%} < threshold {PASS_RATE_THRESHOLD:.2%}; "
        f"failures:\n  " + "\n  ".join(eval_results["failures"])
    )
