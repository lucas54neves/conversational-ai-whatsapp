# Automated Tests — Implementation Plan

**Date:** 2026-04-30
**Source design:** [`docs/specs/2026-04-30-automated-tests-design.md`](specs/2026-04-30-automated-tests-design.md)
**Scope:** Step-by-step execution order to deliver the test suite
described in the design spec. Each phase is one commit, follows
Conventional Commits per `CLAUDE.md`, and ends with explicit
verification commands so it can be validated in isolation.

---

## Phase 1 — Root project metadata and harness scaffolding

**Files:**
- ADD `pyproject.toml` at repo root:
  ```toml
  [project]
  name = "conversational-ai-whatsapp-tests"
  version = "0.0.0"
  requires-python = ">=3.11"
  dependencies = ["nutrition-tools @ file:./mcp-server"]

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
- ADD `tests/__init__.py` (empty)
- ADD `tests/unit/__init__.py` (empty)
- ADD `tests/integration/__init__.py` (empty)
- ADD `tests/conftest.py`:
  - `_postgres_container` session fixture: lazily starts
    `PostgresContainer("postgres:16-alpine")` only when an integration
    test is in the collection. Inspect `request.session.items` and
    skip startup if no item's `nodeid` starts with `tests/integration/`.
  - `_apply_schema(conn)`: reads `db/migrations/001_init.sql` from
    repo root and executes it.
  - `_init_app_pool(url)`: sets `os.environ["DATABASE_URL"]`, then
    imports and calls `nutrition_tools.db.init_pool()`.
  - `seed_module` session fixture: loads `db/seed/seed.py` via
    `importlib.util.spec_from_file_location` and yields the module.
  - `pytest_collection_modifyitems` hook: applies
    `pytest.mark.integration` to every item under `tests/integration/`.
- ADD `tests/unit/test_smoke.py` containing one trivial `assert True`
  test, and `tests/integration/test_smoke.py` containing one trivial
  `assert True` test that requests the `db_url` fixture (proves the
  container path works). Both will be deleted in Phase 5; they exist
  only to validate the harness.

**Verification:**
```bash
pip install -e .[test]
pytest tests/unit/ -v                     # passes, no Docker started
pytest tests/integration/ -v              # passes, container starts/stops
pytest -v                                 # both pass
pytest -m "not integration" -v            # only unit smoke runs
```

**Commit:** `test: scaffold root pytest harness with postgres testcontainer`

---

## Phase 2 — Migrate calculator unit tests

**Files:**
- COPY `mcp-server/tests/test_calculator.py` to
  `tests/unit/test_calculator.py` — content unchanged.
- DELETE `tests/unit/test_smoke.py`

**Verification:**
```bash
pytest tests/unit/ -v                     # 4 tests pass
pytest tests/unit/test_calculator.py::test_male_maintain_matches_mifflin_st_jeor -v
```

**Commit:** `test(unit): migrate calculator tests to tests/unit`

---

## Phase 3 — Migrate tools integration tests and integration conftest

**Files:**
- ADD `tests/integration/conftest.py`:
  - `_seed_taco_minimal(conn)`: a plain helper (not a fixture) that
    runs `TRUNCATE taco_foods CASCADE` and then inserts the three
    reference rows (frango grelhado id=1, arroz branco id=2, feijão
    preto id=3) currently in `mcp-server/tests/conftest.py`.
  - `taco_minimal` autouse function-scoped fixture: invokes
    `_seed_taco_minimal` against a fresh connection at the start of
    each test.
  - `_truncate_logs` autouse function-scoped fixture: after each test,
    `TRUNCATE users, meal_logs CASCADE`. Does not touch `taco_foods`.
- COPY `mcp-server/tests/test_tools.py` to
  `tests/integration/test_tools.py` — content unchanged.
- DELETE `tests/integration/test_smoke.py`

**Verification:**
```bash
pytest tests/integration/test_tools.py -v   # 9 tests pass against the testcontainer
pytest -v                                   # full suite green
```

**Commit:** `test(integration): migrate tools tests with shared TACO fixture`

---

## Phase 4 — Add seed loader integration tests

**Files:**
- ADD `tests/integration/test_seed.py`:
  - Import `seed_module` and `_seed_taco_minimal` (re-exported from
    `tests/integration/conftest.py` if needed, or simply re-implement
    the truncate inline).
  - `test_seed_inserts_full_taco_dataset(seed_module, db_url)`:
    truncate `taco_foods`; call `seed_module.main()`; query
    `SELECT count(*) FROM taco_foods`; assert it equals the data-row
    count of the source TSV (read at test time from the path that
    `seed.py` references — derive it from `seed_module.__file__`).
  - `test_seed_is_idempotent(seed_module, db_url)`: truncate; run
    `main()` twice; assert row count after second run equals row
    count after first.
  - `test_seed_preserves_known_food(seed_module, db_url)`: truncate;
    run `main()`; query for an anchor row (e.g.
    `name ILIKE '%arroz%branco%cozido%'`); assert `calories > 0` and
    every macro column is non-negative.
  - `test_seed_skips_when_already_populated(seed_module, db_url)`:
    pre-populate `taco_foods` with one synthetic row; call `main()`;
    assert the call returns without error and the original row is
    still present. **If `seed.py` lacks a "skip when populated"
    short-circuit, omit this test rather than asserting current
    behavior.** Inspect the file before writing.

**Verification:**
```bash
pytest tests/integration/test_seed.py -v   # all included tests green
pytest -v                                  # full suite still green
```

**Commit:** `test(integration): add coverage for db/seed/seed.py`

---

## Phase 5 — Remove legacy `mcp-server/tests/`

**Files:**
- DELETE `mcp-server/tests/__init__.py`
- DELETE `mcp-server/tests/conftest.py`
- DELETE `mcp-server/tests/test_calculator.py`
- DELETE `mcp-server/tests/test_tools.py`
- DELETE `mcp-server/tests/` (now empty)
- MODIFY `mcp-server/pyproject.toml`:
  - Drop `[project.optional-dependencies] test = ["pytest>=7.0"]`.
  - Drop the `[tool.pytest.ini_options]` block (the root one is
    authoritative).

**Verification:**
```bash
git status                                  # confirms deletions and pyproject.toml edit
test ! -d mcp-server/tests                  # exits 0
pytest -v                                   # full suite still green from root
docker compose build mcp-server             # build still works without test extras
```

**Commit:** `chore(mcp-server): drop test directory and extras (moved to tests/)`

---

## Phase 6 — GitHub Actions workflow

**Files:**
- ADD `.github/workflows/test.yml`:
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

**Verification:**
- `git push` to a feature branch and confirm the workflow appears
  under Actions and passes. (Done after the branch is opened.)
- Locally simulate (no GH Actions runner):
  ```bash
  python3.11 -m venv /tmp/ci-sim && source /tmp/ci-sim/bin/activate
  pip install -e .[test]
  pytest -v                                 # green
  deactivate && rm -rf /tmp/ci-sim
  ```

**Commit:** `ci: add github actions workflow running pytest with testcontainers`

---

## Phase 7 — README update

**Files:**
- MODIFY `README.md`:
  - Add a "Tests" section after the existing setup walkthrough.
    Document:
    - `pip install -e .[test]` to install the harness.
    - `pytest tests/unit/` for the fast loop (no Docker required).
    - `pytest tests/integration/` for the full suite (requires a
      working Docker socket; testcontainers manages the Postgres
      lifecycle).
    - `pytest -m "not integration"` shorthand for the unit-only loop.
  - Mention the CI workflow location (`.github/workflows/test.yml`)
    in the same section.

**Verification:**
- `markdown-link-check README.md` (or manual inspection) passes for
  any new internal links.
- Follow the new "Tests" section verbatim in a fresh shell; both
  commands succeed.

**Commit:** `docs: document local and CI test workflow in readme`

---

## Definition of done (after all 7 phases)

1. `pip install -e .[test] && pytest -v` from the repo root runs the
   complete unit + integration suite against an ephemeral Postgres
   container and exits 0.
2. `pytest tests/unit/` does not start Docker.
3. `mcp-server/tests/` no longer exists; `mcp-server/pyproject.toml`
   carries no test extras and no pytest config.
4. `.github/workflows/test.yml` runs on push and pull_request, and
   passes on the merge commit that closes this work.
5. `db/seed/seed.py` regressions (parsing errors, lost idempotence)
   are caught by `tests/integration/test_seed.py`.
6. README's "Tests" section is sufficient for a new contributor to run
   the suite without consulting any other file.

---

## Cross-cutting reminders

- All test files, fixtures, and CI yaml are written in English per
  `CLAUDE.md`.
- Conventional Commits: `test:` for new test files, `chore:` for
  cleanup, `ci:` for the workflow, `docs:` for the README.
- Run `pytest -v` after each phase before committing — green pre-commit
  is the gate, not just "compiles".
- Do not introduce coverage tooling or a Python-version matrix in this
  plan. Both are explicit non-goals in the spec; opening that door
  belongs in a separate spec.
- The harness assumes Docker is available wherever integration tests
  run. The unit-only path is the escape hatch when Docker is not.
