"""Mock-tier coverage for the tool error contract.

Stubs a registry tool to raise a ToolError, then asserts that the
agent (1) does not retry the failed tool within the turn and
(2) translates the situation into a PT-BR cue for the user.
"""

from __future__ import annotations

from nutrition_tools.errors import TransientDBError, ValidationError

from tests.agent import harness
from tests.agent.fakes import FakeAnthropicClient, FakeResponse
from tests.agent.harness import run_agent

PHONE = "+5511988887766"


def test_agent_handles_transient_error(monkeypatch, agent_db):
    def raise_transient(**_kwargs):
        raise TransientDBError()

    monkeypatch.setitem(harness.TOOL_REGISTRY, "search_food", raise_transient)

    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use("search_food", {"query": "arroz"}),
            FakeResponse.text("Tive um problema momentâneo aqui. Pode reenviar a mensagem?"),
        ]
    )

    result = run_agent(client, ["comi 100g de arroz"])

    # The agent must not retry search_food (or anything else) in the same turn.
    called = [c.name for c in result.tool_calls]
    assert called == ["search_food"]
    # No save_meals was attempted.
    assert "save_meals" not in called
    # Final message contains a PT-BR cue from the AGENTS.md rule.
    lowered = result.final_text.lower()
    assert any(
        cue in lowered for cue in ("reenvi", "tente de novo", "tenta de novo", "tentar de novo")
    ), f"no retry cue in: {result.final_text!r}"


def test_agent_handles_validation_error_during_onboarding(monkeypatch, agent_db):
    def raise_validation(**_kwargs):
        raise ValidationError("weight_kg must be between 20 and 300")

    monkeypatch.setitem(harness.TOOL_REGISTRY, "save_user_profile", raise_validation)

    client = FakeAnthropicClient(
        [
            FakeResponse.tool_use(
                "save_user_profile",
                {
                    "phone": PHONE,
                    "weight_kg": 5,
                    "height_cm": 180,
                    "age": 30,
                    "sex": "M",
                    "goal": "maintain",
                },
            ),
            FakeResponse.text("O peso precisa estar entre 20 e 300 kg. Pode me dizer de novo?"),
        ]
    )

    result = run_agent(client, ["meu peso é 5 kg, altura 180, 30 anos, homem, manter"])

    # The agent must not retry save_user_profile in the same turn.
    called = [c.name for c in result.tool_calls]
    assert called == ["save_user_profile"]
    # Final message surfaces the constraint to the user in PT-BR.
    assert "20" in result.final_text
    assert "300" in result.final_text
