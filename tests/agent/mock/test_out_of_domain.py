"""Mock-tier coverage for out-of-domain redirection.

Asserts the agent does not invoke any tool when faced with a clearly
off-topic question, and that the response contains the documented
redirect copy from `agents/nutrition/AGENTS.md`.
"""

from __future__ import annotations

from tests.agent.fakes import FakeAnthropicClient, FakeResponse
from tests.agent.harness import run_agent


def test_out_of_domain_redirects(agent_db):
    client = FakeAnthropicClient(
        [
            FakeResponse.text(
                "Posso te ajudar a registrar refeições, acompanhar suas metas diárias "
                "ou ver seu histórico semanal. O que prefere?"
            ),
        ]
    )

    result = run_agent(client, ["qual a capital da França?"])

    assert result.tool_calls == []
    assert "registrar refeições" in result.final_text
    assert client.remaining == 0
