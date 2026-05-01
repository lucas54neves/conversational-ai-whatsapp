"""Mock-tier coverage for the onboarding flow.

Asserts the exact tool-call sequence produced when the user has no
profile yet, both for the five-field happy path and for input
validation that must reject obviously bad values without calling
`save_user_profile`.
"""

from __future__ import annotations

import psycopg2

from tests.agent.fakes import FakeAnthropicClient, FakeResponse
from tests.agent.harness import ToolCall, run_agent

PHONE = "+5511999999999"


def _user_count(db_url: str) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM users")
            return cur.fetchone()[0]
    finally:
        conn.close()


def _user_row(db_url: str, phone: str) -> tuple | None:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT weight_kg, height_cm, age, sex, goal FROM users WHERE phone_number = %s",
                (phone,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def test_onboarding_happy_path(agent_db):
    profile_args = {
        "phone": PHONE,
        "weight_kg": 70,
        "height_cm": 175,
        "age": 30,
        "sex": "M",
        "goal": "maintain",
    }
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("get_user_profile", {"phone": PHONE}),
            FakeResponse.text("Vamos começar. Qual seu peso em kg?"),
            FakeResponse.text("E sua altura em cm?"),
            FakeResponse.text("Qual sua idade?"),
            FakeResponse.text("Sexo? M ou F?"),
            FakeResponse.text("Objetivo? lose, maintain ou gain?"),
            FakeResponse.tool_use("save_user_profile", profile_args),
            FakeResponse.text("Perfil salvo. Suas metas diárias estão prontas."),
        ]
    )

    result = run_agent(
        client,
        [PHONE, "70", "175", "30", "M", "maintain"],
    )

    assert result.tool_calls == [
        ToolCall(name="get_user_profile", args={"phone": PHONE}),
        ToolCall(name="save_user_profile", args=profile_args),
    ]
    assert "metas" in result.final_text.lower()
    assert client.remaining == 0

    row = _user_row(agent_db, PHONE)
    assert row is not None
    weight_kg, height_cm, age, sex, goal = row
    assert (float(weight_kg), height_cm, age, sex, goal) == (70.0, 175, 30, "M", "maintain")


def test_onboarding_rejects_out_of_range_weight(agent_db):
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("get_user_profile", {"phone": PHONE}),
            FakeResponse.text("Vamos começar. Qual seu peso em kg?"),
            FakeResponse.text(
                "Peso 5kg está fora do intervalo válido (20–300 kg). "
                "Por favor envie um valor válido."
            ),
        ]
    )

    result = run_agent(client, [PHONE, "5"])

    assert result.tool_calls == [ToolCall(name="get_user_profile", args={"phone": PHONE})]
    assert "5kg" in result.final_text or "5 kg" in result.final_text
    assert _user_count(agent_db) == 0
    assert client.remaining == 0
