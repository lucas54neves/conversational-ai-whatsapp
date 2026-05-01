"""Mock-tier coverage for daily and weekly progress queries.

Pre-seeds a profile and a recent meal so the tools have something to
return, then asserts the agent calls the expected lookups and produces
the documented response shape.
"""

from __future__ import annotations

from nutrition_tools import tools

from tests.agent.fakes import FakeAnthropicClient, FakeResponse
from tests.agent.harness import run_agent

PHONE = "+5511977776666"

ARROZ_ID = 2


def _seed_profile_and_meal(_db_url: str) -> None:
    tools.save_user_profile(PHONE, 70, 175, 30, "M", "maintain")
    tools.save_meals(
        PHONE,
        [{"food_name": "Arroz branco cozido", "taco_food_id": ARROZ_ID, "quantity_g": 100}],
    )


def test_daily_progress_query(agent_db):
    _seed_profile_and_meal(agent_db)
    client = FakeAnthropicClient(
        [
            FakeResponse.multi(
                FakeResponse.tool_use("get_user_profile", {"phone": PHONE}),
                FakeResponse.tool_use("get_daily_summary", {"phone": PHONE}),
            ),
            FakeResponse.text(
                "Hoje: 128 / 2.450 kcal (5%). Proteína 2 / 122g, "
                "Carboidrato 28 / 306g, Gordura 0 / 68g."
            ),
        ]
    )

    result = run_agent(client, ["como estou hoje?"])

    names = {c.name for c in result.tool_calls}
    assert names == {"get_user_profile", "get_daily_summary"}
    assert "Hoje" in result.final_text
    assert client.remaining == 0


def test_weekly_history_query(agent_db):
    _seed_profile_and_meal(agent_db)
    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("get_weekly_history", {"phone": PHONE}),
            FakeResponse.text(
                "Sua semana:\nHoje: 128 kcal ▼\nOntem: 0 kcal ▼\nAnteontem: 0 kcal ▼"
            ),
        ]
    )

    result = run_agent(client, ["minha semana"])

    assert [c.name for c in result.tool_calls] == ["get_weekly_history"]
    assert any(marker in result.final_text for marker in ("✓", "▲", "▼"))
    assert client.remaining == 0
