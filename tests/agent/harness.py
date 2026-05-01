"""Parallel agent loop used by the agent reasoning test tiers.

The harness implements the standard Anthropic tool-use loop against a
client that may be either the real `anthropic.Anthropic` (eval tier) or
`tests.agent.fakes.FakeAnthropicClient` (mock tier). It loads the
production system prompt from `agents/nutrition/AGENTS.md` and the
production model from `agents/nutrition/agent.yaml` so the test
configuration tracks production without manual sync.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from nutrition_tools import tools as _tools
from nutrition_tools.errors import ToolError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agents" / "nutrition"
SYSTEM_PROMPT_PATH = AGENT_DIR / "AGENTS.md"
AGENT_YAML_PATH = AGENT_DIR / "agent.yaml"

_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
    "haiku": "claude-haiku-4-5-20251001",
}


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def load_model_name() -> str:
    override = os.environ.get("AGENT_TEST_MODEL")
    if override:
        return override
    raw = yaml.safe_load(AGENT_YAML_PATH.read_text(encoding="utf-8"))["model"]
    return _MODEL_ALIASES.get(raw, raw)


def _call_get_daily_summary(phone: str, date: str | None = None) -> dict | None:
    return _tools.get_daily_summary(phone, date)


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "search_food": _tools.search_food,
    "save_user_profile": _tools.save_user_profile,
    "get_user_profile": _tools.get_user_profile,
    "save_meals": _tools.save_meals,
    "get_daily_summary": _call_get_daily_summary,
    "get_weekly_history": _tools.get_weekly_history,
}


TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_food",
        "description": (
            "Search for foods in the TACO Brazilian food database. "
            "Returns up to 5 candidates with name and macros per 100g. "
            "Use the returned food id when calling save_meals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "save_user_profile",
        "description": (
            "Save or update a user profile and calculate daily macro targets. "
            "sex must be 'M' or 'F'. goal must be 'lose', 'maintain', or 'gain'. "
            "Targets are calculated via Mifflin-St Jeor with sedentary activity factor (x1.2)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "weight_kg": {"type": "number"},
                "height_cm": {"type": "integer"},
                "age": {"type": "integer"},
                "sex": {"type": "string", "enum": ["M", "F"]},
                "goal": {"type": "string", "enum": ["lose", "maintain", "gain"]},
            },
            "required": ["phone", "weight_kg", "height_cm", "age", "sex", "goal"],
        },
    },
    {
        "name": "get_user_profile",
        "description": (
            "Retrieve a user profile and daily targets. "
            "Returns null when the user has no profile — must trigger onboarding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"phone": {"type": "string"}},
            "required": ["phone"],
        },
    },
    {
        "name": "save_meals",
        "description": (
            "Log one or more meals atomically. "
            "Each item: {food_name, taco_food_id, quantity_g}. "
            "All inserts share a single transaction; "
            "if any food id is invalid nothing is committed. "
            "Only call this after the user has confirmed the meal summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "food_name": {"type": "string"},
                            "taco_food_id": {"type": "integer"},
                            "quantity_g": {"type": "number"},
                        },
                        "required": ["food_name", "taco_food_id", "quantity_g"],
                    },
                },
            },
            "required": ["phone", "items"],
        },
    },
    {
        "name": "get_daily_summary",
        "description": (
            "Get a user's daily meal totals vs. targets. "
            "date format: YYYY-MM-DD. Defaults to today when omitted. "
            "Returns null when the user has no profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "get_weekly_history",
        "description": (
            "Get the last 7 days of daily summaries for a user. "
            "Returns null when the user has no profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"phone": {"type": "string"}},
            "required": ["phone"],
        },
    },
]


def _canonicalize(args: dict) -> dict:
    return json.loads(json.dumps(args, sort_keys=True, default=str))


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass
class RunResult:
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    turns: int = 0


def _execute_tool(name: str, args: dict) -> tuple[Any, bool]:
    """Run a tool and return (content, is_error).

    `is_error=True` mirrors FastMCP's wire shape for a ToolError — the
    tool_result block carries the string "code: message" and sets
    isError on the response. Other unexpected exceptions stay in the
    legacy generic dict so existing tests continue to pass.
    """
    fn = TOOL_REGISTRY[name]
    try:
        return fn(**args), False
    except ToolError as exc:
        return str(exc), True
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)}, False


def run_agent(
    client,
    conversation: list[str],
    *,
    user_phone: str | None = None,
    max_turns: int = 10,
    max_tokens: int = 2048,
) -> RunResult:
    """Drive the agent through one or more user messages.

    `conversation` is the sequence of user turns; between each, the
    assistant runs its tool-use loop until `stop_reason == "end_turn"`
    or `max_turns` is reached (across the entire conversation).

    `user_phone`, when provided, is appended to the system prompt as a
    session-context note so the model has a concrete value to pass
    whenever a tool requires a `phone` argument. Mock-tier tests leave
    it unset because they script the args directly.
    """
    system_text = load_system_prompt()
    if user_phone:
        system_text = (
            f"{system_text}\n\n## Session context\n"
            f"The user's WhatsApp phone number is {user_phone}. "
            f"Use this exact value whenever a tool requires a `phone` argument."
        )
    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    model = load_model_name()

    messages: list[dict] = []
    result = RunResult()

    for user_msg in conversation:
        messages.append({"role": "user", "content": user_msg})

        while True:
            if result.turns >= max_turns:
                raise RuntimeError(
                    f"agent loop exceeded max_turns={max_turns}; "
                    f"recorded {len(result.tool_calls)} tool calls"
                )
            result.turns += 1

            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )

            assistant_blocks = [_block_to_message_dict(b) for b in response.content]
            messages.append({"role": "assistant", "content": assistant_blocks})

            tool_results: list[dict] = []
            for block in response.content:
                btype = getattr(block, "type", None)
                if btype == "tool_use":
                    args = _canonicalize(dict(block.input))
                    result.tool_calls.append(ToolCall(name=block.name, args=args))
                    tool_output, is_error = _execute_tool(block.name, dict(block.input))
                    payload: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output
                        if is_error
                        else json.dumps(tool_output, default=str),
                    }
                    if is_error:
                        payload["is_error"] = True
                    tool_results.append(payload)
                elif btype == "text":
                    result.final_text = block.text

            if response.stop_reason == "end_turn":
                break
            if response.stop_reason == "tool_use" and tool_results:
                messages.append({"role": "user", "content": tool_results})
                continue
            break

    return result


def _block_to_message_dict(block: Any) -> dict:
    btype = getattr(block, "type", None)
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input),
        }
    if btype == "text":
        return {"type": "text", "text": block.text}
    raise ValueError(f"unexpected content block type: {btype!r}")
