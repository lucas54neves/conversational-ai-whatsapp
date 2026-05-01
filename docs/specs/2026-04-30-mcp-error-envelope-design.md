# MCP error envelope — design

## Goal

Stop raw `psycopg2` exceptions from reaching the agent through the MCP
channel. Replace them with a small set of classified errors that carry a
stable code and a short English message, so the nutrition agent can
choose the right behavior (translate validation, ask the user to retry,
apologize and stop) without parsing SQL state codes or stack traces.

The envelope adds **hygiene + classification** only. It does not retry,
does not localize messages in the server, and does not change any tool
return shape on the success path.

## Non-goals

- Automatic server-side retry of transient errors. The user already
  drives the loop (WhatsApp is async); a one-shot retry inside the
  server adds latency and test complexity for marginal gain.
- Portuguese copy in the error payload. Product copy lives in
  `agents/nutrition/AGENTS.md`. The server emits English codes; the
  agent translates.
- Wrapping `tools.py` or `db.py`. Those layers stay native: tools raise
  `ValueError` for input violations and let `psycopg2` errors propagate.
  The existing `tests/integration/test_tools.py` suite — which depends
  on `pytest.raises(ValueError)` against `tools.<func>` directly —
  continues to pass without modification.
- Hiding programmer bugs (`KeyError`, `AssertionError`, `TypeError`).
  Those must crash loudly so they appear in the MCP server log instead
  of being disguised as database errors.
- Structured telemetry (metrics, traces). `logger.exception` is the
  only observability for now. If a dashboard becomes necessary, it is
  a separate spec.
- Running the new behavior through the eval tier. The mock tier proves
  the contract; the eval tier is for semantic regression and is not
  worth the cost for an error-handling change.

## Architecture

### Repository layout after this change

```
conversational-ai-whatsapp-1/
├── agents/nutrition/
│   └── AGENTS.md                                  [MODIFIED]
├── mcp-server/src/nutrition_tools/
│   ├── errors.py                                  [NEW]
│   └── server.py                                  [MODIFIED]
└── tests/
    ├── unit/
    │   └── test_errors.py                         [NEW]
    ├── integration/
    │   └── test_errors.py                         [NEW]
    └── agent/mock/
        └── test_errors.py                         [NEW]
```

`tools.py`, `db.py`, `calculator.py`, and the existing test files are
not touched.

### Error module — `mcp-server/src/nutrition_tools/errors.py`

Contains:

1. A base exception `ToolError(Exception)` with attributes `code: str`
   and `message: str`. Its `__str__` returns `f"{code}: {message}"`,
   which is what FastMCP serializes back to the agent.
2. Three concrete subclasses, one per code:
   - `ValidationError(message)` — sets `code = "validation_error"`.
   - `TransientDBError(message="database temporarily unavailable")` —
     sets `code = "transient_db_error"`.
   - `PermanentDBError(message="database operation failed")` —
     sets `code = "permanent_db_error"`.
3. `classify(exc: BaseException) -> ToolError | None`. Maps a raw
   exception to a `ToolError` or returns `None` if the exception is not
   recognized (so the decorator re-raises it untouched).
4. The `mcp_safe` decorator, described below.

### Mapping table inside `classify()`

| Raw exception | Returned `ToolError` |
|---|---|
| `ValueError` | `ValidationError(str(exc))` |
| `psycopg2.OperationalError` | `TransientDBError()` |
| `psycopg2.InterfaceError` | `TransientDBError()` |
| `psycopg2.pool.PoolError` | `TransientDBError()` |
| any other `psycopg2.Error` (`IntegrityError`, `DataError`, `ProgrammingError`, `InternalError`) | `PermanentDBError()` |
| anything else | `None` (re-raised by the decorator) |

`psycopg2.pool.PoolError` does not inherit from `psycopg2.Error`, so it
must be imported and handled explicitly. The unit test for `classify()`
covers it as its own case to prevent silent regressions.

### The `mcp_safe` decorator

Logical flow:

```
@mcp_safe
def wrapped(*args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        logger.exception("tool %s failed", func.__name__)
        wrapped_exc = classify(exc)
        if wrapped_exc is None:
            raise
        raise wrapped_exc from exc
```

The decorator logs the full traceback server-side via
`logger.exception` before re-raising. The payload that reaches the
agent is only `f"{code}: {message}"` — no SQL, no stack frames, no
table or column names.

### Application in `server.py`

Each `@mcp.tool()` function gets `@mcp_safe` applied **below** the
`@mcp.tool()` decorator:

```python
@mcp.tool()
@mcp_safe
def search_food(query: str) -> list[dict]:
    ...
```

Decorator order matters. Python applies decorators bottom-up, so
`mcp_safe` wraps the function first, and `mcp.tool()` registers the
already-wrapped version. Reversing the order would let raw exceptions
escape because `mcp.tool` would call the unwrapped function. This is
called out explicitly in `AGENTS.md` and verified by the integration
test.

All six tools (`search_food`, `save_user_profile`, `get_user_profile`,
`save_meals`, `get_daily_summary`, `get_weekly_history`) get the
decorator.

## Agent contract

A new section is added to `agents/nutrition/AGENTS.md`, between
"Out-of-domain messages" and "Response style":

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

The PT-BR examples are illustrative, not mandatory templates — the
agent keeps the freedom of tone defined elsewhere in the prompt; this
section only fixes *what to communicate*.

## Test plan

### Unit — `tests/unit/test_errors.py`

Exercises `classify()` and `mcp_safe` in isolation, with no Postgres.
Uses `caplog` to assert logging side effects.

| Case | Assertion |
|---|---|
| `classify(ValueError("x"))` | returns `ValidationError`, `message == "x"` |
| `classify(psycopg2.OperationalError(...))` | returns `TransientDBError` |
| `classify(psycopg2.InterfaceError(...))` | returns `TransientDBError` |
| `classify(psycopg2.pool.PoolError(...))` | returns `TransientDBError` |
| `classify(psycopg2.IntegrityError(...))` | returns `PermanentDBError` |
| `classify(psycopg2.DataError(...))` | returns `PermanentDBError` |
| `classify(psycopg2.ProgrammingError(...))` | returns `PermanentDBError` |
| `classify(KeyError("x"))` | returns `None` |
| `mcp_safe(func_that_returns_42)()` | returns `42`, no log |
| `mcp_safe(func_that_raises_ValueError("x"))()` | raises `ValidationError("x")`, `logger.exception` called once |
| `mcp_safe(func_that_raises_KeyError("x"))()` | raises `KeyError`, not `ToolError`, `logger.exception` called once |
| `str(ValidationError("x"))` | `"validation_error: x"` |
| `str(TransientDBError())` | `"transient_db_error: database temporarily unavailable"` |
| `str(PermanentDBError())` | `"permanent_db_error: database operation failed"` |

### Integration — `tests/integration/test_errors.py`

One end-to-end case proving the decorator is wired into the real
`@mcp.tool()` registration:

| Case | Setup | Assertion |
|---|---|---|
| `test_transient_error_when_pool_closed` | `db.init_pool()`, then `db._pool.closeall()`, then invoke the decorated `server.get_user_profile` (whichever attribute FastMCP exposes for the underlying callable in the version pinned by `pyproject.toml` — the planner picks the right accessor) | raises `TransientDBError` |

`permanent_db_error` is not tested at this tier — forcing an
`IntegrityError` would require schema gymnastics that distract from
what the integration test is meant to prove (that the decorator is
plugged in). The unit test already covers the mapping.

### Agent mock — `tests/agent/mock/test_errors.py`

Two cases driving the existing mock harness with stubbed tool failures:

| Case | Scripted tool behavior | Assertions |
|---|---|---|
| `test_agent_handles_transient_error` | first `search_food` call raises `TransientDBError` | (1) the agent does not call any tool a second time within the turn; (2) the final assistant message contains a PT-BR cue from `{"reenvi", "tente de novo", "tenta de novo"}`; (3) no `save_meals` is called |
| `test_agent_handles_validation_error_during_onboarding` | `save_user_profile` raises `ValidationError("weight_kg must be between 20 and 300")` | (1) the agent does not call `save_user_profile` a second time within the turn; (2) the final assistant message mentions both `"20"` and `"300"` (the constraint reached the user in PT-BR) |

This tier is the only place that proves the loop closes: error code →
prompt rule → user-facing PT-BR message. If anyone changes a code in
`errors.py` without updating `AGENTS.md`, one of these tests fails.

### What is not tested

- Eval tier (real Anthropic API). The mock tier covers the regression;
  the eval tier is reserved for semantic behavior and is not worth the
  cost for an error-handling change.
- `permanent_db_error` end-to-end through the agent. Behavior is
  symmetric to `transient` ("apologize, do not retry"); a second mock
  case would duplicate coverage.

## Risks and mitigations

1. **Prompt and code drift.** A new code added to `errors.py` without
   an `AGENTS.md` update leaves the agent with a code it cannot
   interpret. *Mitigation:* the agent mock tests fail because their
   text assertions stop matching. No structural enforcement — accepted
   given the small surface (3 codes).

2. **`OperationalError` as false-positive transient.** `psycopg2`
   raises `OperationalError` for some non-transient cases (invalid
   credentials, missing database). The pool is initialized once in
   `main()`, so those cases crash the server before any tool runs and
   never reach the decorator. In runtime, `OperationalError` is almost
   always a lost connection. Risk accepted.

3. **`PoolError` does not inherit from `psycopg2.Error`.** It is
   imported from `psycopg2.pool` and listed as its own branch in
   `classify()`. The unit test case for it prevents accidental removal.

4. **Decorator order.** `@mcp_safe` must sit below `@mcp.tool()` in
   each declaration. Reversing the order silently re-introduces the
   bug. Documented inline in `server.py` and verified by the
   integration test.

5. **Verbose logs.** `logger.exception` runs on every failure, which
   may produce noise during a Postgres outage. Accepted — silence
   during an outage is worse than noise.
