# Automated tests — design

## Goal

Establish a single, conventional Python test suite at the repo root that
covers the MCP server (`mcp-server/src/nutrition_tools/`) and the TACO
seed loader (`db/seed/seed.py`). Tests are split into unit (no I/O) and
integration (Postgres-backed) layers, and run automatically on every
push and pull request via GitHub Actions.

## Non-goals

- Testing shell scripts under `scripts/`. They are thin wrappers over
  external CLIs (`omni`, `docker`, `genie`) with significant external
  state, and the cost of mocking outweighs the value.
- Testing the agent runtime, NATS plumbing, or end-to-end WhatsApp
  message flow. Out of scope for this iteration.
- Coverage reporting (pytest-cov). Can be added later once a baseline
  exists.
- Python version matrix. The project pins `>=3.11` and runs in a single
  Docker image; testing one version is sufficient.

## Architecture

### Repository layout after this change

```
conversational-ai-whatsapp-1/
├── pyproject.toml              [NEW]
├── tests/                      [NEW]
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_calculator.py        (migrated)
│   └── integration/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_tools.py             (migrated)
│       └── test_seed.py        [NEW]
├── mcp-server/
│   ├── pyproject.toml          (drop the [test] extra)
│   ├── src/nutrition_tools/...
│   └── tests/                  [REMOVED]
└── .github/
    └── workflows/
        └── test.yml            [NEW]
```

### Root `pyproject.toml`

A new top-level project file declares the test harness and pulls
`nutrition-tools` in as an editable local dependency. The project name
is `conversational-ai-whatsapp-tests` (purely a label — never published).

```toml
[project]
name = "conversational-ai-whatsapp-tests"
version = "0.0.0"
requires-python = ">=3.11"
dependencies = [
    "nutrition-tools @ file:./mcp-server",
]

[project.optional-dependencies]
test = [
    "pytest>=7.0",
    "testcontainers[postgres]>=4.0",
    "psycopg2-binary>=2.9.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: requires a postgres container (started by tests/conftest.py)",
]
```

`db/seed/seed.py` is **not** promoted to a package. It is loaded inside
`tests/conftest.py` via `importlib.util.spec_from_file_location` and
exposed as a `seed_module` fixture, since the file is a one-off script.

### Local developer workflow

```
pip install -e .[test]
pytest tests/unit/         # fast, no Docker
pytest tests/integration/  # spins up Postgres container
pytest                     # full suite
```

`testcontainers` requires a working Docker socket on the host. The
project already depends on Docker for the runtime stack, so this adds
no new operational requirement.

## Components

### `tests/conftest.py` — root harness

Responsibilities:

1. **Postgres container, session-scoped.** Start
   `PostgresContainer("postgres:16-alpine")` exactly once per pytest
   session, but only if the collected tests include any item under
   `tests/integration/`. Pure-unit runs (`pytest tests/unit/`) skip the
   Docker startup entirely. The gating is implemented via a fixture
   that inspects `request.session.items` lazily.
2. **Schema bootstrap.** Connect to the container, run
   `db/migrations/001_init.sql` against it, commit.
3. **Environment wiring.** Export `DATABASE_URL` pointing at the
   container so `nutrition_tools.db.init_pool()` reads it on first
   import. Call `nutrition_tools.db.init_pool()` exactly once after the
   schema is in place.
4. **`seed_module` fixture.** Load `db/seed/seed.py` via `importlib`
   and yield the module object so integration tests can call it
   directly without subprocess overhead.
5. **Auto-mark integration.** A `pytest_collection_modifyitems` hook
   adds `pytest.mark.integration` to every item whose `nodeid` starts
   with `tests/integration/`. Lets devs run
   `pytest -m "not integration"` for a quick loop.

### `tests/integration/conftest.py` — integration helpers

1. **Minimal TACO seed helper** — a plain function (not a fixture)
   that wipes `taco_foods` and inserts three reference rows (frango
   grelhado, arroz branco, feijão preto). Reused by both the global
   autouse fixture below and by `test_seed.py`'s teardown.
2. **`taco_minimal` fixture**, function-scoped, autouse with
   `pytest.fixture(autouse=True)`: invokes the helper above before
   each test in `tests/integration/`. The reset is per-test instead of
   per-session because `test_seed.py` swaps `taco_foods` for the full
   dataset, and the next test in any order needs the minimal subset
   restored. The cost is negligible (three INSERTs).
3. **Per-test truncate**, function-scoped, autouse:
   `TRUNCATE users, meal_logs CASCADE`. Does **not** touch
   `taco_foods` — that table is owned by `taco_minimal`.

### `tests/unit/test_calculator.py`

Migrated verbatim from `mcp-server/tests/test_calculator.py`. Tests
`calculate_targets` (Mifflin-St Jeor, macro splits, lose/gain offsets).
No DB, no I/O.

### `tests/integration/test_tools.py`

Migrated verbatim from `mcp-server/tests/test_tools.py`. Tests
`get_user_profile`, `save_user_profile`, `save_meals`,
`get_daily_summary`, `get_weekly_history`, `search_food`. Depends on
the minimal TACO seed and on `nutrition_tools.db` being initialized.

### `tests/integration/test_seed.py` — new

Covers `db/seed/seed.py`. The `taco_minimal` autouse fixture runs
first and seeds the three reference rows; each `test_seed_*` test then
calls `TRUNCATE taco_foods CASCADE` itself before exercising the
loader. After the test ends, the next test's `taco_minimal` invocation
restores the minimal seed automatically — no special teardown needed.

Tests:

1. **`test_seed_inserts_full_taco_dataset`** — call `seed_module.main()`
   on an empty `taco_foods`; assert row count matches the number of
   data rows in the source TSV (computed by reading the file at test
   time, not hard-coded).
2. **`test_seed_is_idempotent`** — call `seed_module.main()` twice;
   assert the row count is unchanged after the second run. Catches
   regressions in the `ON CONFLICT` upsert.
3. **`test_seed_preserves_known_food`** — after seeding, query an
   anchor food (e.g. `name ILIKE '%arroz%branco%cozido%'`); assert
   `calories > 0` and all macros are non-negative. Catches column
   misalignment or decimal-parsing regressions.
4. **`test_seed_skips_when_already_populated`** — pre-populate
   `taco_foods` with one row; run `seed_module.main()`; assert no error
   and that the seed completes. Only included if `seed.py` has a
   short-circuit guard. If it does not, this test is omitted rather
   than asserting current behavior we don't want to lock in.

## CI workflow

`.github/workflows/test.yml`:

```yaml
name: tests
on: [push, pull_request]

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e .[test]
      - run: pytest -v
```

Notes:

- GitHub-hosted `ubuntu-latest` runners ship with Docker, which is all
  testcontainers needs. No `services: postgres:` is declared because
  the test harness manages its own container.
- Single job, single Python version. Adding a matrix is deferred until
  there is a reason.
- Branch protection (require this check before merge) is configured in
  GitHub's UI and is out of scope for this implementation. Documented
  here as a follow-up task for the repository owner.

## Migration plan

1. Create root `pyproject.toml` with the contents above.
2. Create `tests/`, `tests/unit/`, `tests/integration/` and the
   `__init__.py` files.
3. Move `mcp-server/tests/test_calculator.py` to
   `tests/unit/test_calculator.py` (no content changes — it imports
   from `nutrition_tools.calculator`, which keeps working).
4. Move `mcp-server/tests/test_tools.py` to
   `tests/integration/test_tools.py`.
5. Replace the existing `mcp-server/tests/conftest.py` with the new
   split: container/schema/seed-module bits go into
   `tests/conftest.py`; minimal TACO seed and per-test truncate go
   into `tests/integration/conftest.py`.
6. Delete `mcp-server/tests/` entirely.
7. Remove `[project.optional-dependencies] test = ["pytest>=7.0"]`
   from `mcp-server/pyproject.toml`.
8. Remove the `[tool.pytest.ini_options]` block from
   `mcp-server/pyproject.toml` (the new root one supersedes it).
9. Write `tests/integration/test_seed.py`.
10. Add `.github/workflows/test.yml`.
11. Update README with the new local commands
    (`pip install -e .[test]`, `pytest`).
12. Verify locally: `pytest tests/unit/`,
    `pytest tests/integration/`, then `pytest` — all green.

## Risks and mitigations

- **testcontainers requires Docker.** Documented as a prereq in the
  README. CI runners already have it. Devs running `pytest tests/unit/`
  alone never need Docker — the container fixture is gated on having
  integration tests in the collection.
- **Cold start on every CI run (~3-5s for postgres:16-alpine).**
  Acceptable. If it ever bites, the runner-provided `services:` syntax
  is a drop-in replacement.
- **`importlib`-loaded `seed.py` won't be re-loadable mid-session.**
  The fixture resolves it once per session and yields the module
  object; tests don't reload it. Acceptable.

## Open questions

None at design time. If `seed.py` turns out to lack a "skip when
populated" short-circuit, the corresponding test is dropped per the
note in `test_seed.py`.
