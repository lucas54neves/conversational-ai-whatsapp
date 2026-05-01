"""Per-test fixtures for the eval (real-API) tier.

This subtree is opt-in via `pytest -m agent_eval` and skipped entirely
when `ANTHROPIC_API_KEY` is unset, so a default `pytest` invocation
never spends real API budget. The session-scoped `eval_results`
collector lets `test_runner.py` report a single aggregate pass-rate
threshold across cases.
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/agent/eval/" in item.nodeid.replace(os.sep, "/"):
            item.add_marker(pytest.mark.agent_eval)


@pytest.fixture(autouse=True)
def _require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; agent_eval requires real API access")


@pytest.fixture(scope="session")
def real_anthropic_client():
    import anthropic

    return anthropic.Anthropic()


@pytest.fixture(scope="session")
def eval_results() -> dict:
    return {"pass": 0, "fail": 0, "failures": []}
