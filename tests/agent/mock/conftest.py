"""Apply the agent_mock marker autouse to every test in this subtree."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/agent/mock/" in item.nodeid.replace(os.sep, "/"):
            item.add_marker(pytest.mark.agent_mock)
