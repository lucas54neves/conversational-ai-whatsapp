"""Scripted fake of `anthropic.Anthropic` for the mock test tier.

The harness only touches `client.messages.create(...)`. The fake pops
the next response from a list each time `create` is called and raises
when the list is empty — that emptiness is the assertion that the
agent loop made exactly the expected number of model calls.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

_id_counter = itertools.count(start=1)


def _next_tool_use_id() -> str:
    return f"toolu_fake_{next(_id_counter)}"


@dataclass
class _ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[Any]
    stop_reason: str


class FakeResponse:
    """Builder for scripted responses returned by `FakeAnthropicClient`."""

    @staticmethod
    def tool_use(name: str, args: dict, *, tool_use_id: str | None = None) -> _FakeMessage:
        block = _ToolUseBlock(
            id=tool_use_id or _next_tool_use_id(),
            name=name,
            input=dict(args),
        )
        return _FakeMessage(content=[block], stop_reason="tool_use")

    @staticmethod
    def text(s: str) -> _FakeMessage:
        return _FakeMessage(content=[_TextBlock(text=s)], stop_reason="end_turn")

    @staticmethod
    def multi(*blocks: Any) -> _FakeMessage:
        materialized: list[Any] = []
        has_tool_use = False
        for block in blocks:
            if isinstance(block, _FakeMessage):
                materialized.extend(block.content)
            elif isinstance(block, (_ToolUseBlock, _TextBlock)):
                materialized.append(block)
            else:
                raise TypeError(f"FakeResponse.multi: unsupported block type {type(block)!r}")
            if any(getattr(b, "type", None) == "tool_use" for b in materialized):
                has_tool_use = True
        return _FakeMessage(
            content=materialized,
            stop_reason="tool_use" if has_tool_use else "end_turn",
        )


class _FakeMessages:
    def __init__(self, responses: list[_FakeMessage]):
        self._responses = list(responses)
        self._call_count = 0

    def create(self, **kwargs) -> _FakeMessage:
        self._call_count += 1
        if not self._responses:
            raise AssertionError(
                f"FakeAnthropicClient: ran out of scripted responses on call "
                f"#{self._call_count}; messages.create called with model="
                f"{kwargs.get('model')!r} and "
                f"{len(kwargs.get('messages', []))} messages"
            )
        return self._responses.pop(0)


class FakeAnthropicClient:
    """Drop-in stand-in for `anthropic.Anthropic` used by the mock tier."""

    def __init__(self, responses: list[_FakeMessage]):
        self.messages = _FakeMessages(responses)

    @property
    def remaining(self) -> int:
        return len(self.messages._responses)
