# MCP Error Envelope — Implementation Plan

**Date:** 2026-04-30
**Source design:** [`docs/specs/2026-04-30-mcp-error-envelope-design.md`](specs/2026-04-30-mcp-error-envelope-design.md)
**Scope:** Step-by-step execution order to deliver the MCP error
envelope described in the design spec. Each phase is one commit,
follows Conventional Commits per `CLAUDE.md`, and ends with explicit
verification commands so it can be validated in isolation.

All shell commands assume the venv is active:

```bash
source .venv/bin/activate
```

---

## Phase 1 — Add the `errors` module with unit tests

Self-contained module with no dependency on `server.py` or `tools.py`.
Lands first so subsequent phases can import from it.

**Files:**

- ADD `mcp-server/src/nutrition_tools/errors.py`:
  ```python
  """Tool error envelope for the nutrition MCP server.

  Maps raw exceptions raised by `tools.py` (validation `ValueError`s and
  `psycopg2` exceptions) to a small set of classified `ToolError`
  subclasses with stable `code` strings. The agent reads the code to
  decide whether to translate a constraint, ask the user to retry, or
  apologize and stop.
  """

  from __future__ import annotations

  import functools
  import logging
  from collections.abc import Callable
  from typing import Any, TypeVar

  import psycopg2
  import psycopg2.pool

  logger = logging.getLogger(__name__)

  F = TypeVar("F", bound=Callable[..., Any])


  class ToolError(Exception):
      code: str = "tool_error"

      def __init__(self, message: str) -> None:
          super().__init__(message)
          self.message = message

      def __str__(self) -> str:
          return f"{self.code}: {self.message}"


  class ValidationError(ToolError):
      code = "validation_error"


  class TransientDBError(ToolError):
      code = "transient_db_error"

      def __init__(self, message: str = "database temporarily unavailable") -> None:
          super().__init__(message)


  class PermanentDBError(ToolError):
      code = "permanent_db_error"

      def __init__(self, message: str = "database operation failed") -> None:
          super().__init__(message)


  def classify(exc: BaseException) -> ToolError | None:
      if isinstance(exc, ValueError):
          return ValidationError(str(exc))
      if isinstance(exc, psycopg2.pool.PoolError):
          return TransientDBError()
      if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
          return TransientDBError()
      if isinstance(exc, psycopg2.Error):
          return PermanentDBError()
      return None


  def mcp_safe(func: F) -> F:
      @functools.wraps(func)
      def wrapper(*args: Any, **kwargs: Any) -> Any:
          try:
              return func(*args, **kwargs)
          except Exception as exc:
              logger.exception("tool %s failed", func.__name__)
              wrapped = classify(exc)
              if wrapped is None:
                  raise
              raise wrapped from exc

      return wrapper  # type: ignore[return-value]
  ```

- ADD `tests/unit/test_errors.py`:
  ```python
  import logging

  import psycopg2
  import psycopg2.pool
  import pytest
  from nutrition_tools.errors import (
      PermanentDBError,
      TransientDBError,
      ValidationError,
      classify,
      mcp_safe,
  )


  def test_classify_value_error_preserves_message():
      wrapped = classify(ValueError("weight_kg must be between 20 and 300"))
      assert isinstance(wrapped, ValidationError)
      assert wrapped.message == "weight_kg must be between 20 and 300"


  def test_classify_operational_error_is_transient():
      assert isinstance(classify(psycopg2.OperationalError("boom")), TransientDBError)


  def test_classify_interface_error_is_transient():
      assert isinstance(classify(psycopg2.InterfaceError("boom")), TransientDBError)


  def test_classify_pool_error_is_transient():
      # PoolError does not inherit from psycopg2.Error — must be matched explicitly.
      assert isinstance(classify(psycopg2.pool.PoolError("boom")), TransientDBError)


  def test_classify_integrity_error_is_permanent():
      assert isinstance(classify(psycopg2.IntegrityError("boom")), PermanentDBError)


  def test_classify_data_error_is_permanent():
      assert isinstance(classify(psycopg2.DataError("boom")), PermanentDBError)


  def test_classify_programming_error_is_permanent():
      assert isinstance(classify(psycopg2.ProgrammingError("boom")), PermanentDBError)


  def test_classify_unrelated_exception_returns_none():
      assert classify(KeyError("k")) is None
      assert classify(AssertionError()) is None


  def test_mcp_safe_passes_return_value_through(caplog):
      caplog.set_level(logging.ERROR)
      decorated = mcp_safe(lambda x: x * 2)
      assert decorated(21) == 42
      assert caplog.records == []


  def test_mcp_safe_wraps_value_error(caplog):
      caplog.set_level(logging.ERROR)

      @mcp_safe
      def boom():
          raise ValueError("bad input")

      with pytest.raises(ValidationError) as ei:
          boom()
      assert ei.value.message == "bad input"
      assert ei.value.__cause__ is not None  # `raise X from exc` preserved
      assert any("tool boom failed" in r.message for r in caplog.records)


  def test_mcp_safe_does_not_wrap_unknown_exceptions(caplog):
      caplog.set_level(logging.ERROR)

      @mcp_safe
      def boom():
          raise KeyError("k")

      with pytest.raises(KeyError):
          boom()
      # Still logged so programmer bugs surface in the MCP server log.
      assert any("tool boom failed" in r.message for r in caplog.records)


  def test_str_format_matches_wire_payload():
      assert str(ValidationError("x")) == "validation_error: x"
      assert str(TransientDBError()) == "transient_db_error: database temporarily unavailable"
      assert str(PermanentDBError()) == "permanent_db_error: database operation failed"
  ```

**Verification:**
```bash
pytest tests/unit/test_errors.py -v
pytest -v   # full suite stays green
```

**Commit:** `feat(mcp): add ToolError envelope and mcp_safe decorator`

---

## Phase 2 — Apply the decorator at the MCP boundary, prove with integration test

Wire `mcp_safe` into every `@mcp.tool()` registration in `server.py`,
then add one integration test that proves the decorator is plugged into
the real FastMCP-registered callable (not just unit-tested in isolation).

**Files:**

- MODIFY `mcp-server/src/nutrition_tools/server.py`:
  - Import `from .errors import mcp_safe`.
  - Apply `@mcp_safe` **below** `@mcp.tool()` on each of the six tool
    declarations. Decorator order matters — `mcp.tool` must register the
    already-wrapped function. Example:
    ```python
    @mcp.tool()
    @mcp_safe
    def search_food(query: str) -> list[dict]:
        """Search for foods in the TACO Brazilian food database.

        Returns up to 5 candidates with name and macros per 100g.
        Use the returned food id when calling save_meal.
        """
        return t.search_food(query)
    ```
  - Add a one-line comment above the first decorated tool noting that
    `@mcp_safe` must remain below `@mcp.tool()`. Do not add comments
    on every tool — one is enough.
  - Apply to all six: `search_food`, `save_user_profile`,
    `get_user_profile`, `save_meals`, `get_daily_summary`,
    `get_weekly_history`.

- ADD `tests/integration/test_errors.py`:
  ```python
  """Prove that the @mcp_safe decorator is wired into the real
  @mcp.tool() registrations and translates raw psycopg2 errors at the
  boundary."""

  from __future__ import annotations

  import pytest
  from nutrition_tools import db, server
  from nutrition_tools.errors import TransientDBError

  PHONE = "+5511900000099"


  def _decorated_callable(mcp_tool):
      """Resolve the underlying callable wrapped by FastMCP's @mcp.tool().

      FastMCP versions differ in how they expose the original function —
      try the common attribute names, fall back to calling the object
      directly if it stayed callable.
      """
      for attr in ("fn", "func", "callback", "handler"):
          fn = getattr(mcp_tool, attr, None)
          if callable(fn):
              return fn
      if callable(mcp_tool):
          return mcp_tool
      raise AssertionError(
          f"could not find underlying callable on {type(mcp_tool).__name__}"
      )


  def test_transient_error_when_pool_closed(_db_url_fixture_unused):
      # The integration conftest already initialized db._pool against the
      # testcontainer. Close it to force psycopg2.pool.PoolError on getconn.
      assert db._pool is not None
      db._pool.closeall()
      try:
          fn = _decorated_callable(server.get_user_profile)
          with pytest.raises(TransientDBError) as ei:
              fn(PHONE)
          assert ei.value.code == "transient_db_error"
      finally:
          # Re-init for any subsequent test in the session.
          db.init_pool()
  ```

  Notes for the implementer:
  - The fixture name in the parameter list (`_db_url_fixture_unused`)
    must match whatever `tests/integration/conftest.py` exposes that
    triggers `db.init_pool()` and pool population. Read that conftest
    first; rename the parameter to match (commonly `db_url` or
    `agent_db`). The body uses `db._pool` directly, not the fixture
    value.
  - This is the only integration test added in this phase. No
    `permanent_db_error` integration coverage — the unit suite already
    verifies the mapping; forcing an `IntegrityError` end-to-end would
    require schema changes that distract from what the test proves.

**Verification:**
```bash
pytest tests/integration/test_errors.py -v
pytest -v   # full suite — including the existing tests/integration/test_tools.py
            # which still relies on tools.<func> raising native ValueError
```

**Commit:** `feat(mcp): apply mcp_safe to all nutrition tool registrations`

---

## Phase 3 — Update the agent system prompt

Add the "Tool errors" section to `agents/nutrition/AGENTS.md`. Pure
docs change — no code, no tests.

**Files:**

- MODIFY `agents/nutrition/AGENTS.md`: insert the following section
  between `## Out-of-domain messages` and `## Response style`:

  ```markdown
  ## Tool errors

  When a tool returns an error, the payload is `code: message` in English.
  Never show the code or the raw English message to the user — translate
  the situation into PT-BR following the rules below. Do **not** retry the
  same call within the same turn unless the rule says so.

  | Code | Meaning | What to do |
  |------|---------|------------|
  | `validation_error` | The value you sent is outside accepted ranges (e.g., `weight_kg must be between 20 and 300`). | Translate the constraint into PT-BR and ask the user to provide a valid value. Common during onboarding. Example: "O peso precisa estar entre 20 e 300 kg. Pode me dizer de novo?" |
  | `transient_db_error` | A momentary infrastructure issue. | Apologize briefly and ask the user to send the message again. Example: "Tive um problema momentâneo aqui. Pode reenviar?" Do not call the tool again in this turn. |
  | `permanent_db_error` | A persistent system problem. | Apologize and suggest trying again later. Example: "Estou com um problema técnico no momento. Tente de novo em alguns minutos." Do not call the tool again. |
  ```

**Verification:**
```bash
grep -n "## Tool errors" agents/nutrition/AGENTS.md
grep -n "validation_error\|transient_db_error\|permanent_db_error" agents/nutrition/AGENTS.md
pytest -v   # full suite stays green; no new tests yet for this section
```

**Commit:** `docs(agent): document tool error codes in nutrition system prompt`

---

## Phase 4 — Make the agent harness ToolError-aware

The harness in `tests/agent/harness.py` currently catches every
exception inside `_execute_tool` and serializes it as
`{"error": type, "message": ...}` in the tool_result content. That
shape never reaches production (the production wire format from FastMCP
on a `ToolError` is `isError=True` with text `"code: message"`). To let
the mock tier prove the agent contract end-to-end, the harness must
serialize `ToolError` exactly the way FastMCP does.

**Files:**

- MODIFY `tests/agent/harness.py`:
  - Import `from nutrition_tools.errors import ToolError`.
  - Replace `_execute_tool` with:
    ```python
    def _execute_tool(name: str, args: dict) -> tuple[Any, bool]:
        """Run a tool and return (content, is_error).

        `is_error=True` mirrors FastMCP's wire shape for a ToolError —
        the tool_result block carries the string "code: message" and
        sets isError on the response. Other unexpected exceptions stay
        in the legacy generic dict so existing tests continue to pass.
        """
        fn = TOOL_REGISTRY[name]
        try:
            return fn(**args), False
        except ToolError as exc:
            return str(exc), True
        except Exception as exc:
            return {"error": type(exc).__name__, "message": str(exc)}, False
    ```
  - Update the call site in `run_agent` (currently
    `tool_output = _execute_tool(block.name, dict(block.input))`) to
    receive both values and pass `is_error` into the tool_result block:
    ```python
    tool_output, is_error = _execute_tool(block.name, dict(block.input))
    payload: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": tool_output if is_error else json.dumps(tool_output, default=str),
    }
    if is_error:
        payload["is_error"] = True
    tool_results.append(payload)
    ```

  Notes for the implementer:
  - Existing mock and eval tests must keep passing — `is_error=True`
    only fires when a `ToolError` is raised from the registry, which
    none of the current scripted scenarios trigger.
  - `TOOL_REGISTRY` continues to point at raw `nutrition_tools.tools`
    functions. New mock tests in Phase 5 monkey-patch entries to raise
    `ToolError` directly. The harness does not import `server.py`, so
    no decorator runs inside the harness — the `ToolError` is
    constructed by the test stub.

**Verification:**
```bash
pytest tests/agent/mock/ -v   # all existing mock tests still pass
pytest -v
```

**Commit:** `test(agent-harness): serialize ToolError as FastMCP-style is_error result`

---

## Phase 5 — Agent mock tests for the error contract

The capstone — proves that error code → AGENTS.md rule → user-facing
PT-BR message is a closed loop. If anyone changes a code in `errors.py`
without updating `AGENTS.md`, one of these tests fails.

**Files:**

- ADD `tests/agent/mock/test_errors.py`:
  ```python
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
              FakeResponse.text(
                  "Tive um problema momentâneo aqui. Pode reenviar a mensagem?"
              ),
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
          cue in lowered
          for cue in ("reenvi", "tente de novo", "tenta de novo", "tentar de novo")
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
              FakeResponse.text(
                  "O peso precisa estar entre 20 e 300 kg. Pode me dizer de novo?"
              ),
          ]
      )

      result = run_agent(client, ["meu peso é 5 kg, altura 180, 30 anos, homem, manter"])

      # The agent must not retry save_user_profile in the same turn.
      called = [c.name for c in result.tool_calls]
      assert called == ["save_user_profile"]
      # Final message surfaces the constraint to the user in PT-BR.
      assert "20" in result.final_text
      assert "300" in result.final_text
  ```

  Notes for the implementer:
  - Both tests rely on the existing `agent_db` fixture from
    `tests/agent/conftest.py` to keep the rest of the harness happy
    (system prompt loaded, model alias resolved). The DB is unused in
    these tests because the stubbed registry entry raises before any
    SQL runs.
  - The text assertions are loose on purpose. The system prompt
    examples are illustrative; the test accepts any PT-BR retry cue
    from a small allowlist.

**Verification:**
```bash
pytest tests/agent/mock/test_errors.py -v
pytest tests/agent/mock/ -v   # the rest of the mock tier still passes
pytest -v                     # full suite green
```

**Commit:** `test(agent-mock): cover transient and validation tool error contract`

---

## Out of plan (per spec)

- No retry logic in the server.
- No PT-BR copy in the error payload.
- No telemetry beyond `logger.exception`.
- No eval tier coverage for error codes.
- No changes to `tools.py`, `db.py`, or `tests/integration/test_tools.py`.
- No `permanent_db_error` integration test (covered by unit only).

## Cross-phase checklist before opening a PR

```bash
pre-commit run --all-files
pytest -v
```

Both must be clean. The pytest hook in `.pre-commit-config.yaml`
already runs the full suite, so the second command is a redundant
sanity check.
