# Agent reasoning tests — design

## Goal

Add regression coverage for the nutrition agent's reasoning — the
mapping from user messages to tool-call sequences and resulting
database state — on top of the existing unit (calculator) and
integration (MCP tools over Postgres) suites.

The coverage is split into two tiers that run independently:

- **Mock tier** — deterministic, in-process, runs on every commit and
  PR via the existing pytest gate. A fake Anthropic client emits
  scripted tool-use sequences against a parallel agent loop wired to
  the real MCP tool functions and a Postgres testcontainer. Asserts
  on exact tool-call sequences and final DB state.
- **Eval tier** — opt-in, calls the real Anthropic API, runs nightly
  and on demand via a dedicated GitHub Actions workflow. Drives the
  same harness with the production system prompt and asserts on a
  looser contract (tool subset membership, DB state predicates,
  forbidden tools, response keywords). Aggregates a pass-rate
  threshold across cases.

## Non-goals

- Testing Genie or Omni themselves. Genie's agent loop and Omni's
  channel bridge are third-party software exercised by `doctor.sh` as
  a manual smoke check. The risk of divergence between Genie's loop
  and our parallel harness is accepted.
- Testing response style (tone, emoji usage, decimal formatting,
  exact template layout). These would require a judge LLM, which is
  out of scope for this iteration.
- Running the eval tier in PR CI. The cost and flakiness of real LLM
  calls do not belong on the per-PR gate.
- Adding a judge LLM, vector-similarity scoring, or any
  semantic-equivalence check on assistant text beyond keyword
  membership.
- Replacing the existing integration tests in `tests/integration/`.
  Those keep covering the MCP tools in isolation; the agent tier
  covers them as called by an LLM.

## Architecture

### Repository layout after this change

```
conversational-ai-whatsapp-1/
├── pyproject.toml                       [MODIFIED]
├── tests/
│   ├── unit/                            (existing)
│   ├── integration/                     (existing)
│   └── agent/                           [NEW]
│       ├── __init__.py
│       ├── harness.py                   agent loop, tool dispatcher, prompt loader
│       ├── fakes.py                     FakeAnthropicClient
│       ├── conftest.py                  agent_db fixture, harness factory
│       ├── mock/
│       │   ├── __init__.py
│       │   ├── conftest.py              autouse agent_mock marker
│       │   ├── test_onboarding.py
│       │   ├── test_meal_logging.py
│       │   ├── test_queries.py
│       │   └── test_out_of_domain.py
│       └── eval/
│           ├── __init__.py
│           ├── conftest.py              autouse agent_eval marker + API key skip
│           ├── cases.yaml               eval dataset
│           └── test_runner.py           parametrized runner over cases.yaml
└── .github/workflows/
    ├── test.yml                         (existing, unchanged)
    └── eval.yml                         [NEW]
```

### Harness (`tests/agent/harness.py`)

A single function `run_agent(client, conversation) -> RunResult` that
implements the standard Anthropic tool-use loop:

1. Load the system prompt from `agents/nutrition/AGENTS.md` at runtime
   (so prompt drift is observable in tests).
2. Read the model name from `agents/nutrition/agent.yaml` (so test
   configuration tracks production configuration).
3. For each turn: call `client.messages.create(...)`. If the response
   contains `tool_use` blocks, execute the corresponding Python
   functions, append `tool_result` blocks to the conversation, and
   loop. Stop on `end_turn` or when `max_turns` (default 10) is
   reached.
4. Return a `RunResult` containing the canonicalized list of tool
   calls (name + JSON-normalized args), the final assistant text, and
   a snapshot helper for DB-state assertions.

The harness binds the six MCP tools as Python functions imported
directly from `nutrition_tools.tools`. They share the testcontainer
Postgres connection — no MCP server process, no SSE transport.

System prompt caching (`cache_control: ephemeral`) is enabled in the
`messages.create` call. The prompt is large and stable; without
caching, the eval tier costs roughly 3× more.

### Fake client (`tests/agent/fakes.py`)

`FakeAnthropicClient` mimics the subset of `anthropic.Anthropic` the
harness uses (only `messages.create`). Constructed with a list of
scripted responses; each call pops the next response. An empty list
on a subsequent call raises — this is how mock tests assert "the
model was called exactly N times".

Each scripted response is built from helpers:

```python
FakeResponse.tool_use("search_food", {"query": "arroz"})
FakeResponse.text("Confirmado: ...")
FakeResponse.multi(
    FakeResponse.tool_use("search_food", {"query": "arroz"}),
    FakeResponse.tool_use("search_food", {"query": "frango"}),
)
```

The fake does not interpret the system prompt. Mock tests are
deterministic by construction.

### Database fixtures

`tests/agent/conftest.py` reuses `tests/conftest.py`'s
`postgres_container` session fixture. A new function-scoped
`agent_db` fixture truncates `users`, `meal_logs`, and dependent
tables between tests (the seeded `taco_foods` table is preserved —
re-seeding per test is too slow).

### Eval cases (`tests/agent/eval/cases.yaml`)

Each case has the shape:

```yaml
- name: meal_log_simple
  conversation:
    - "comi 100g de arroz no almoço"
    - "sim"
  expected_tools_subset: [search_food, save_meals]
  forbidden_tools: []
  expected_db:
    meal_logs_count: 1
    kcal_range: [110, 160]
  expected_assistant_response_contains: []
  max_turns: 10
```

`expected_tools_subset` and `forbidden_tools` are sets — order is not
asserted at this tier. `expected_db` is a small DSL of predicates
(`meal_logs_count`, `kcal_range`, `users_count`, ...). All fields
except `name` and `conversation` are optional and default to no
constraint.

### Eval runner (`tests/agent/eval/test_runner.py`)

```python
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_eval_case(case, agent_db, real_anthropic_client):
    result = run_agent(real_anthropic_client, case["conversation"])
    record_pass_or_fail(case, result)

def test_aggregate_pass_rate():
    assert pass_rate() >= PASS_RATE_THRESHOLD
```

Per-case results are recorded in a session-scoped collector. The
final `test_aggregate_pass_rate` test fails the suite if the rate
falls below the constant `PASS_RATE_THRESHOLD = 0.85` (declared at
the top of the file; bumping it is an explicit PR change).

### Pytest configuration

`pyproject.toml` gains the `anthropic` SDK in the test extras (used
by the harness against both the fake and real clients) and two new
markers:

```toml
markers = [
    "integration: requires a postgres container (started by tests/conftest.py)",
    "agent_mock: agent loop tests with FakeAnthropicClient (deterministic)",
    "agent_eval: agent loop tests against the real Anthropic API (costs money, opt-in)",
]
```

`tests/agent/mock/conftest.py` applies `agent_mock` autouse to
everything under `mock/`. `tests/agent/eval/conftest.py` applies
`agent_eval` autouse to everything under `eval/` and skips when
`ANTHROPIC_API_KEY` is unset:

```python
@pytest.fixture(autouse=True)
def _require_api_key():
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; agent_eval requires real API access")
```

`pytest` with no args runs unit + integration + agent_mock. The
agent_eval tier is opt-in via `pytest -m agent_eval`.

### CI workflows

`.github/workflows/test.yml` is unchanged — the existing `pytest -v`
picks up the agent_mock tier automatically because no marker filter
is applied.

`.github/workflows/eval.yml` (new):

```yaml
name: eval
on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * *"   # 03:00 UTC-3
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[test]"
      - run: pytest -m agent_eval -v
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Failure surfaces via the standard GitHub Actions email notification.
No custom alerting in this iteration.

### Pre-commit

`.pre-commit-config.yaml` is unchanged. The existing `pytest` hook
runs the agent_mock tier as part of the default pytest invocation —
no API key, no extra cost. The eval tier is skipped because it
requires the marker filter and the API key.

### README

A new subsection under `## Tests` documents:

- How to run the mock tier locally (`pytest tests/agent/mock/`).
- How to run the eval tier locally (`ANTHROPIC_API_KEY=... pytest -m agent_eval`).
- Where the nightly eval runs and where to read its results
  (Actions tab → eval workflow).

## Test scenarios

### Mock tier (10 initial cases, strict assertions)

| # | File | Scenario | Tool sequence |
|---|---|---|---|
| 1 | `test_onboarding.py` | Happy path, 5 fields | `get_user_profile→null` then 5 text turns then `save_user_profile` |
| 2 | `test_onboarding.py` | Rejects out-of-range weight (5 kg) | `get_user_profile→null` then text rejecting input, no `save_user_profile` |
| 3 | `test_meal_logging.py` | Single item: "comi 100g de arroz" | `search_food("arroz")` then text confirmation then `save_meals([1 item])` after "sim" |
| 4 | `test_meal_logging.py` | Multi-item: arroz + frango | `search_food` × 2 then `save_meals([2 items])` in one call |
| 5 | `test_meal_logging.py` | No confirmation, no save | `search_food` then confirmation then user silent, no `save_meals` |
| 6 | `test_meal_logging.py` | Cancellation ("não") | `search_food` then confirmation then "não", no `save_meals`, DB unchanged |
| 7 | `test_meal_logging.py` | Missing quantity | "comi arroz" then text asking quantity, no `search_food` |
| 8 | `test_queries.py` | Daily progress | `get_user_profile` + `get_daily_summary(today)` |
| 9 | `test_queries.py` | Weekly history | `get_weekly_history` |
| 10 | `test_out_of_domain.py` | "Capital da França?" | Zero tool calls, redirect text |

### Eval tier (15 initial cases, loose assertions)

The 10 mock scenarios re-expressed as natural-language inputs, plus
five LLM-variability cases that the mock tier cannot meaningfully
cover:

- **Code-switching** — "had 100g of rice" must still produce a
  PT-BR response and the same tool sequence as the PT input.
- **Implicit quantity** — "uma colher de arroz" must trigger a
  clarifying question, not a guessed quantity.
- **Multi-turn meal split** — items spread across two messages
  ("comi arroz" then "e 200g de frango") must accumulate in a
  single `save_meals` call.
- **Insidious OOD** — "qual a melhor dieta para emagrecer?" must
  redirect briefly without offering medical advice.
- **Partial onboarding** — user volunteers three fields in one
  message ("tenho 30 anos, 70kg, M"); agent must request only the
  missing two.

## Operational details

### Cost

Eval tier per run: ~15 cases × ~5 turns × ~2k tokens (input + output,
with system-prompt caching) ≈ 150k tokens.

At Sonnet pricing with cache hits dominating input cost: ~$0.30 per
full run, ~$10/month with the daily cron.

### Threshold policy

`PASS_RATE_THRESHOLD = 0.85` is a constant at the top of
`test_runner.py`. Raising it is an explicit PR. The starting value
allows ~2 failures across 15 cases — enough headroom to add new cases
without the whole suite turning red on a single regression, while
still flagging consistent degradation.

### Adding cases

New eval cases are YAML-only edits to `cases.yaml`. No code change.
Mock cases are new tests in the corresponding `mock/test_*.py` file
following the existing structure.

### Model tracking

The harness reads the model name from `agents/nutrition/agent.yaml`
rather than hardcoding it. Production model upgrades are reflected in
tests automatically; an explicit override (`AGENT_TEST_MODEL` env
var) is available for ad-hoc model comparisons.

### Risks accepted

- **Genie loop divergence** — the parallel harness does not call
  Genie. If Claude Code's tool-use protocol changes, the mock tier
  may keep passing while production breaks. The eval tier (real API)
  and `doctor.sh` (real Genie) catch this with delay.
- **Prompt drift** — the harness reads `AGENTS.md` at test time.
  Prompt edits can break tests with no code change. This is desired
  behavior: it forces test review on prompt changes.
- **Eval flakiness** — even at temperature 0, the API may return
  different tool sequences between runs. The 0.85 threshold and
  subset-based assertions absorb routine variance; sustained drops
  surface a real regression.
