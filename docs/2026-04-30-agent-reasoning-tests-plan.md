# Agent Reasoning Tests — Implementation Plan

**Date:** 2026-04-30
**Source design:** [`docs/specs/2026-04-30-agent-reasoning-tests-design.md`](specs/2026-04-30-agent-reasoning-tests-design.md)
**Scope:** Step-by-step execution order to deliver the agent reasoning
test suite described in the design spec. Each phase is one commit,
follows Conventional Commits per `CLAUDE.md`, and ends with explicit
verification commands so it can be validated in isolation.

---

## Phase 1 — Add `anthropic` SDK to test extras and declare new markers

**Files:**
- MODIFY `pyproject.toml`:
  - Append `"anthropic>=0.40"` to `[project.optional-dependencies] test`.
  - Append `"pyyaml>=6.0"` to the same list (used by the eval runner
    to load `cases.yaml`).
  - Extend `[tool.pytest.ini_options].markers`:
    ```toml
    markers = [
        "integration: requires a postgres container (started by tests/conftest.py)",
        "agent_mock: agent loop tests with FakeAnthropicClient (deterministic)",
        "agent_eval: agent loop tests against the real Anthropic API (costs money, opt-in)",
    ]
    ```

**Verification:**
```bash
source .venv/bin/activate
pip install -e .[test]
python -c "import anthropic, yaml; print(anthropic.__version__, yaml.__version__)"
pytest --markers | grep -E "agent_(mock|eval)"
pytest -v                                    # existing suite stays green
```

**Commit:** `chore(deps): add anthropic and pyyaml to test extras for agent harness`

---

## Phase 2 — Harness scaffolding (loop, fake client, fixtures)

**Files:**
- ADD `tests/agent/__init__.py` (empty)
- ADD `tests/agent/harness.py`:
  - `PROJECT_ROOT = Path(__file__).resolve().parents[2]`.
  - `load_system_prompt() -> str`: reads
    `agents/nutrition/AGENTS.md` from `PROJECT_ROOT`.
  - `load_model_name() -> str`: reads `agents/nutrition/agent.yaml`
    via `yaml.safe_load`, returns the `model` key. Resolves the
    aliases declared there (e.g. `sonnet`) to the full model id used
    by `messages.create` (`claude-sonnet-4-6`); fall back to the raw
    string when no alias matches. Honors `AGENT_TEST_MODEL` override.
  - `TOOL_REGISTRY: dict[str, Callable]` mapping the six MCP tool
    names to functions imported from `nutrition_tools.tools`.
  - `TOOL_SCHEMAS: list[dict]` — the JSONSchema declarations passed
    to `messages.create(tools=...)`. Schemas mirror the docstrings in
    `mcp-server/src/nutrition_tools/server.py`. Build them once at
    import time; do not derive at runtime.
  - `@dataclass class ToolCall`: `name: str`, `args: dict`
    (canonicalized via `json.dumps(sort_keys=True)` then re-parsed).
  - `@dataclass class RunResult`: `tool_calls: list[ToolCall]`,
    `final_text: str`, `turns: int`.
  - `run_agent(client, conversation: list[str], max_turns: int = 10) -> RunResult`:
    standard Anthropic tool-use loop. Conversation list items become
    sequential user turns — between each user turn the assistant runs
    its tool-use loop until `stop_reason == "end_turn"` (then the
    next user turn is appended). System prompt sent with
    `cache_control: {"type": "ephemeral"}`. Raises `RuntimeError` if
    `max_turns` is reached.
- ADD `tests/agent/fakes.py`:
  - `@dataclass class _ToolUseBlock`: `id: str`, `name: str`,
    `input: dict`, `type: Literal["tool_use"] = "tool_use"`.
  - `@dataclass class _TextBlock`: `text: str`,
    `type: Literal["text"] = "text"`.
  - `@dataclass class _FakeMessage`: `content: list[Any]`,
    `stop_reason: str`. The harness reads `.content` and
    `.stop_reason` only.
  - `class FakeResponse`: classmethods `tool_use(name, args)`,
    `text(s)`, and `multi(*blocks)`. Each builds a `_FakeMessage`
    with `stop_reason` `"tool_use"` for tool-use responses and
    `"end_turn"` for plain text.
  - `class FakeAnthropicClient`:
    - `__init__(self, responses: list[_FakeMessage])`.
    - `self.messages = self`.
    - `def create(self, **kwargs) -> _FakeMessage`: pops `responses[0]`,
      returns it. Raises `AssertionError` if list is empty (with the
      kwargs in the message for debuggability).
- ADD `tests/agent/conftest.py`:
  - Reuse the `postgres_container`, `db_url`, and
    `taco_minimal`/`_truncate_logs` fixtures already in
    `tests/conftest.py` and `tests/integration/conftest.py`. Import
    the `db_url` fixture explicitly so agent tests participate in the
    same Postgres lifecycle.
  - `agent_db` function-scoped fixture: composes the existing
    truncate fixtures so each test starts with a clean `users` and
    `meal_logs` and the seeded TACO rows intact. Yields the live
    `psycopg2` connection from `nutrition_tools.db.get_pool()`.
  - `pytest_collection_modifyitems`: apply
    `pytest.mark.integration` to every item under `tests/agent/` (so
    they participate in the existing Postgres container lifecycle
    started by `tests/conftest.py`).

**Verification:**
```bash
source .venv/bin/activate
python -c "from tests.agent.harness import load_system_prompt, load_model_name, TOOL_REGISTRY, TOOL_SCHEMAS; \
           assert len(TOOL_REGISTRY) == 6 and len(TOOL_SCHEMAS) == 6; \
           print(load_model_name(), len(load_system_prompt()))"
python -c "from tests.agent.fakes import FakeAnthropicClient, FakeResponse; \
           c = FakeAnthropicClient([FakeResponse.text('hi')]); \
           print(c.messages.create().content[0].text)"
pytest -v                                    # full suite still green; no new tests yet
```

**Commit:** `test(agent): scaffold reasoning harness with fake anthropic client`

---

## Phase 3 — Mock tier: marker autouse + onboarding tests

**Files:**
- ADD `tests/agent/mock/__init__.py` (empty)
- ADD `tests/agent/mock/conftest.py`:
  - `pytest_collection_modifyitems`: apply `pytest.mark.agent_mock`
    to every item under `tests/agent/mock/`.
- ADD `tests/agent/mock/test_onboarding.py`:
  - `test_onboarding_happy_path(agent_db)`:
    Scripted responses (in order):
    1. `tool_use("get_user_profile", {"phone": "+5511999999999"})`
    2. `text("Qual seu peso em kg?")`
    3. `text("Qual sua altura em cm?")`
    4. `text("Qual sua idade?")`
    5. `text("Qual seu sexo? M/F")`
    6. `text("Qual seu objetivo? lose/maintain/gain")`
    7. `tool_use("save_user_profile", {...full profile...})`
    8. `text("Perfil salvo. Suas metas...")`
    Conversation = `["oi", "70", "175", "30", "M", "maintain"]`.
    Asserts:
    - `result.tool_calls == [ToolCall("get_user_profile", {...}),
       ToolCall("save_user_profile", {...})]`
    - `agent_db` query for the user row matches the saved profile.
    - `result.final_text` contains "metas".
  - `test_onboarding_rejects_out_of_range_weight(agent_db)`:
    Scripted: `tool_use("get_user_profile", null)` → `text("Peso 5kg
    está fora do intervalo válido (20-300kg). Por favor envie um peso
    válido.")`.
    Conversation = `["oi", "5"]`.
    Asserts:
    - `result.tool_calls == [ToolCall("get_user_profile", {...})]` —
      no `save_user_profile`.
    - `agent_db` `users` table is empty.

**Verification:**
```bash
source .venv/bin/activate
pytest tests/agent/mock/test_onboarding.py -v
pytest -m agent_mock -v
pytest -v                                    # full suite green
```

**Commit:** `test(agent-mock): cover onboarding happy path and validation rejection`

---

## Phase 4 — Mock tier: meal-logging tests (5 cases)

**Files:**
- ADD `tests/agent/mock/test_meal_logging.py`:
  - `test_single_item_meal_log(agent_db)` — "comi 100g de arroz" →
    `search_food` → confirmation text → "sim" → `save_meals` with
    one item. Asserts sequence and one row in `meal_logs`.
  - `test_multi_item_single_save_meals(agent_db)` — "150g arroz +
    200g frango" → two `search_food` calls → confirmation → "sim" →
    **one** `save_meals` call with two items. Asserts the
    `save_meals` args list has length 2.
  - `test_no_confirmation_no_save(agent_db)` — `search_food` →
    confirmation → next user turn is also a confirmation request
    (silence simulated as repeated prompt) → assistant does **not**
    emit `save_meals`. Asserts `meal_logs` is empty.
  - `test_cancellation_discards_meal(agent_db)` — `search_food` →
    confirmation → "não" → assistant returns text acknowledging
    cancellation. Asserts no `save_meals` and `meal_logs` empty.
  - `test_missing_quantity_asks_first(agent_db)` — "comi arroz" →
    assistant asks for quantity, **no** `search_food`. Asserts the
    only tool calls (if any) are profile lookups, never `search_food`
    or `save_meals`.

**Verification:**
```bash
source .venv/bin/activate
pytest tests/agent/mock/test_meal_logging.py -v
pytest -m agent_mock -v                      # 7 mock tests green so far
```

**Commit:** `test(agent-mock): cover meal logging confirmation, multi-item, and edge cases`

---

## Phase 5 — Mock tier: query and OOD tests

**Files:**
- ADD `tests/agent/mock/test_queries.py`:
  - `test_daily_progress_query(agent_db)` — pre-seed `users` row and
    one `meal_logs` row via direct SQL. Conversation = `["como
    estou hoje?"]`. Scripted: `tool_use("get_user_profile", ...)` +
    `tool_use("get_daily_summary", {"phone": ...})` (single
    parallel-tool turn) → `text("Hoje (...)")`. Asserts both tool
    calls appear (order not asserted within a single turn) and final
    text contains "Hoje".
  - `test_weekly_history_query(agent_db)` — pre-seed user + a few
    daily logs. Conversation = `["minha semana"]`. Scripted:
    `tool_use("get_weekly_history", ...)` → text with `✓`/`▲`/`▼`
    markers. Asserts the single tool call and presence of at least
    one marker.
- ADD `tests/agent/mock/test_out_of_domain.py`:
  - `test_out_of_domain_redirects(agent_db)` — Conversation =
    `["qual a capital da França?"]`. Scripted: single `text(...)`
    response with redirect copy. Asserts `result.tool_calls == []`
    and the text contains "registrar refeições" or similar redirect
    keyword.

**Verification:**
```bash
source .venv/bin/activate
pytest tests/agent/mock/ -v                  # 10 mock tests green
pytest -v                                    # full suite green
```

**Commit:** `test(agent-mock): cover daily/weekly queries and out-of-domain redirect`

---

## Phase 6 — Eval tier: runner, conftest, dataset

**Files:**
- ADD `tests/agent/eval/__init__.py` (empty)
- ADD `tests/agent/eval/conftest.py`:
  - `pytest_collection_modifyitems`: apply `pytest.mark.agent_eval`
    to every item under `tests/agent/eval/`.
  - `_require_api_key` autouse fixture: `pytest.skip(...)` when
    `os.environ.get("ANTHROPIC_API_KEY")` is empty.
  - `real_anthropic_client` session-scoped fixture: returns
    `anthropic.Anthropic()` (reads the env var).
  - `eval_results` session-scoped fixture: a list collector
    (`pass_count`, `fail_count`, `failures: list[str]`). Yielded
    once per session; flushed to a session attribute via
    `pytest_sessionfinish` for the aggregate test.
- ADD `tests/agent/eval/cases.yaml` with 15 cases:
  10 natural-language variants of the mock scenarios + the 5
  variability cases enumerated in the spec
  (code-switching, implicit quantity, multi-turn split, insidious
  OOD, partial onboarding). Schema documented in the spec.
- ADD `tests/agent/eval/test_runner.py`:
  - `PASS_RATE_THRESHOLD = 0.85` at module top.
  - `_load_cases() -> list[dict]` reads `cases.yaml` once.
  - `_assert_case(case, result, agent_db)` applies, in order:
    `expected_tools_subset` (set membership), `forbidden_tools`
    (disjoint check), `expected_db` predicates (`meal_logs_count`
    via `SELECT count(*)`, `kcal_range` via aggregate sum),
    `expected_assistant_response_contains` (case-insensitive
    substring check). Each predicate is its own `assert` so failures
    point at the rule that fired.
  - `@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])`
    `def test_eval_case(case, agent_db, real_anthropic_client, eval_results):`
    Runs `run_agent`, calls `_assert_case` inside a try/except that
    appends to `eval_results` either way (so a single hard failure
    does not cap the run early).
  - `def test_aggregate_pass_rate(eval_results):` — runs after all
    parametrized cases (declared **after** the parametrized test in
    the file; rely on pytest's default in-order collection). Asserts
    `eval_results.pass_count / total >= PASS_RATE_THRESHOLD`. The
    failure message lists the failing case names.

**Verification:**
```bash
source .venv/bin/activate
pytest -m agent_eval -v                      # all skipped without ANTHROPIC_API_KEY
ANTHROPIC_API_KEY=$REAL_KEY pytest -m agent_eval -v   # 15 cases run, threshold check passes
pytest -v                                    # full default suite stays green
                                             # (eval skipped because no key in default env)
```

**Commit:** `test(agent-eval): add real-API regression suite with pass-rate threshold`

---

## Phase 7 — GitHub Actions eval workflow

**Files:**
- ADD `.github/workflows/eval.yml`:
  ```yaml
  name: eval
  on:
    workflow_dispatch:
    schedule:
      - cron: "0 6 * * *"   # 03:00 UTC-3 daily
  jobs:
    eval:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.11"
            cache: pip
        - run: pip install -e .[test]
        - run: pytest -m agent_eval -v
          env:
            ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  ```

**Verification:**
- After push: open the Actions tab, manually dispatch the `eval`
  workflow, confirm it runs, the key is read from the secret, and
  the threshold passes.
- The repo secret `ANTHROPIC_API_KEY` must be set before the
  workflow can pass — document this in the README phase below.

**Commit:** `ci: add nightly eval workflow against the real anthropic api`

---

## Phase 8 — README documentation

**Files:**
- MODIFY `README.md` `## Tests` section:
  - Append a `### Agent reasoning tests` subsection covering:
    - **Mock tier:** `pytest tests/agent/mock/`. Runs in the
      default `pytest` invocation (and therefore in the pre-commit
      pytest hook and the `test.yml` CI workflow). No API key
      required.
    - **Eval tier:** `ANTHROPIC_API_KEY=... pytest -m agent_eval`.
      Skipped when the key is unset. Runs nightly via
      `.github/workflows/eval.yml`; results visible under the
      Actions tab.
    - **Adding cases:** new mock scenarios are new functions in the
      relevant `tests/agent/mock/test_*.py`. New eval cases are
      YAML appendices in `tests/agent/eval/cases.yaml` — no code
      change required.
    - **Threshold:** the eval suite fails when fewer than 85% of
      cases pass. The constant lives at the top of
      `tests/agent/eval/test_runner.py`.
  - Add a `## Repo secrets` note (or extend an existing
    "Configuration" subsection) documenting that the
    `ANTHROPIC_API_KEY` GitHub secret must be set for the nightly
    eval workflow.

**Verification:**
- Read the updated README front-to-back; the new subsection is
  consistent with the rest of the document's tone and link style.
- A new contributor can run `pytest tests/agent/mock/` and
  `pytest -m agent_eval` purely from the README.

**Commit:** `docs: document agent reasoning test tiers and eval workflow`

---

## Definition of done (after all 8 phases)

1. `pytest -v` from the repo root runs unit + integration +
   `agent_mock` tiers and exits 0 in under 60 seconds (mock tier
   adds no real LLM latency).
2. `pytest -m agent_eval` skips cleanly without `ANTHROPIC_API_KEY`
   and runs all 15 cases when the key is set, asserting the 0.85
   pass-rate threshold.
3. `.github/workflows/eval.yml` runs nightly and on
   `workflow_dispatch`, reads `ANTHROPIC_API_KEY` from secrets, and
   produces a green run (or a clearly attributable failure) within
   the first manual dispatch after merge.
4. `agents/nutrition/AGENTS.md` edits that change tool-call
   intent break the mock tier; edits that change tone or wording
   without changing intent do not.
5. Adding a new eval case requires a single YAML edit; adding a
   mock case requires a single new test function in an existing
   file.
6. The README `## Tests` section is sufficient for a new
   contributor to run both tiers without consulting any other file.

---

## Cross-cutting reminders

- All test files, fixtures, YAML, and CI yaml are written in
  English per `CLAUDE.md`.
- Conventional Commits per phase header — never combine phases into
  a single commit.
- Activate `.venv` before each commit so the pre-commit pytest hook
  finds `pytest` on `PATH`.
- Do **not** add a judge LLM, vector similarity, or response-style
  assertions in this plan. Both are explicit non-goals in the spec
  and belong in a separate spec.
- The mock tier must remain truly deterministic: never wire in a
  real API call from a `tests/agent/mock/` file, and never read
  `ANTHROPIC_API_KEY` from that subtree.
- The eval tier must not run as part of the default `pytest`
  invocation — the marker filter is the boundary that keeps PR CI
  free and offline.
