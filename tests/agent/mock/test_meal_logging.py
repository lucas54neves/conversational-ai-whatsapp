"""Mock-tier coverage for the meal logging flow.

Each scenario scripts a deterministic tool-call sequence and asserts
both the sequence and the resulting `meal_logs` state. The agent must
search before confirming, only save after explicit user confirmation,
and combine multi-item meals into a single `save_meals` call.
"""

from __future__ import annotations

import psycopg2
from nutrition_tools import tools

from tests.agent.fakes import FakeAnthropicClient, FakeResponse
from tests.agent.harness import ToolCall, run_agent

PHONE = "+5511988887777"

ARROZ_ID = 2
FRANGO_ID = 1


def _seed_user(_db_url: str) -> None:
    tools.save_user_profile(PHONE, 70, 175, 30, "M", "maintain")


def _meal_log_count(db_url: str) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM meal_logs WHERE phone_number = %s", (PHONE,))
            return cur.fetchone()[0]
    finally:
        conn.close()


def _meal_log_rows(db_url: str) -> list[tuple]:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT taco_food_id, quantity_g FROM meal_logs "
                "WHERE phone_number = %s ORDER BY id",
                (PHONE,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def test_single_item_meal_log(agent_db):
    _seed_user(agent_db)
    save_args = {
        "phone": PHONE,
        "items": [
            {"food_name": "Arroz branco cozido", "taco_food_id": ARROZ_ID, "quantity_g": 100},
        ],
    }
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("search_food", {"query": "arroz"}),
            FakeResponse.text("Confirmado: Arroz branco cozido (100g) — 128 kcal. Confirma?"),
            FakeResponse.tool_use("save_meals", save_args),
            FakeResponse.text("Salvo."),
        ]
    )

    result = run_agent(client, ["comi 100g de arroz", "sim"])

    assert result.tool_calls == [
        ToolCall(name="search_food", args={"query": "arroz"}),
        ToolCall(name="save_meals", args=save_args),
    ]
    rows = _meal_log_rows(agent_db)
    assert rows == [(ARROZ_ID, 100.0)]
    assert client.remaining == 0


def test_multi_item_single_save_meals(agent_db):
    _seed_user(agent_db)
    save_args = {
        "phone": PHONE,
        "items": [
            {"food_name": "Arroz branco cozido", "taco_food_id": ARROZ_ID, "quantity_g": 150},
            {"food_name": "Frango grelhado", "taco_food_id": FRANGO_ID, "quantity_g": 200},
        ],
    }
    client = FakeAnthropicClient(
        [
            FakeResponse.multi(
                FakeResponse.tool_use("search_food", {"query": "arroz"}),
                FakeResponse.tool_use("search_food", {"query": "frango"}),
            ),
            FakeResponse.text("Confirmado: arroz (150g) + frango (200g) — 630 kcal. Confirma?"),
            FakeResponse.tool_use("save_meals", save_args),
            FakeResponse.text("Salvo."),
        ]
    )

    result = run_agent(client, ["150g de arroz e 200g de frango", "sim"])

    save_calls = [c for c in result.tool_calls if c.name == "save_meals"]
    assert len(save_calls) == 1, "save_meals must be called exactly once with both items"
    assert save_calls[0].args == save_args
    rows = _meal_log_rows(agent_db)
    assert sorted(rows) == sorted([(ARROZ_ID, 150.0), (FRANGO_ID, 200.0)])
    assert client.remaining == 0


def test_no_confirmation_no_save(agent_db):
    _seed_user(agent_db)
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("search_food", {"query": "arroz"}),
            FakeResponse.text("Confirmado: Arroz branco cozido (100g) — 128 kcal. Confirma?"),
            FakeResponse.text("Sem problema, me avise quando estiver pronto para confirmar."),
        ]
    )

    result = run_agent(client, ["comi 100g de arroz", "ainda não, espera um pouco"])

    assert [c.name for c in result.tool_calls] == ["search_food"]
    assert _meal_log_count(agent_db) == 0
    assert client.remaining == 0


def test_cancellation_discards_meal(agent_db):
    _seed_user(agent_db)
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("search_food", {"query": "arroz"}),
            FakeResponse.text("Confirmado: Arroz branco cozido (100g) — 128 kcal. Confirma?"),
            FakeResponse.text("Sem problema, descartei. O que deseja corrigir?"),
        ]
    )

    result = run_agent(client, ["comi 100g de arroz", "não"])

    assert [c.name for c in result.tool_calls] == ["search_food"]
    assert _meal_log_count(agent_db) == 0
    assert client.remaining == 0


def test_missing_quantity_asks_first(agent_db):
    _seed_user(agent_db)
    client = FakeAnthropicClient(
        [
            FakeResponse.text("Quantos gramas de arroz você comeu?"),
        ]
    )

    result = run_agent(client, ["comi arroz"])

    assert "search_food" not in [c.name for c in result.tool_calls]
    assert "save_meals" not in [c.name for c in result.tool_calls]
    assert _meal_log_count(agent_db) == 0
    assert client.remaining == 0
