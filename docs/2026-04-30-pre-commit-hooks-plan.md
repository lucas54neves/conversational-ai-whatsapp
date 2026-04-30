# Pre-commit Hooks — Implementation Plan

**Date:** 2026-04-30
**Source design:** [`docs/specs/2026-04-30-pre-commit-hooks-design.md`](specs/2026-04-30-pre-commit-hooks-design.md)
**Scope:** Step-by-step execution order to deliver the git hook
configuration described in the design spec. Each phase is one commit,
follows Conventional Commits per `CLAUDE.md`, and ends with explicit
verification commands so it can be validated in isolation.

The phases are ordered so that the toolchain is wired up *before* the
hooks themselves are installed. This avoids a chicken-and-egg situation
where the hooks would block the very commits that introduce them.

---

## Phase 1 — Add ruff config and `dev` extras to `pyproject.toml`

**Files:**
- MODIFY `pyproject.toml`:
  - Under `[project.optional-dependencies]`, add a new `dev` group
    next to the existing `test` group:
    ```toml
    dev = [
        "pre-commit>=3.7",
        "ruff>=0.8",
    ]
    ```
  - Append the ruff configuration at the end of the file:
    ```toml
    [tool.ruff]
    target-version = "py311"
    line-length = 100
    extend-exclude = [".venv", "build", "*.egg-info"]

    [tool.ruff.lint]
    select = [
        "E", "W",   # pycodestyle errors and warnings
        "F",        # pyflakes
        "I",        # isort
        "B",        # flake8-bugbear
        "UP",       # pyupgrade
        "SIM",      # flake8-simplify
    ]
    ignore = []

    [tool.ruff.format]
    quote-style = "double"
    ```

**Verification:**
```bash
pip install -e ".[test,dev]"     # installs ruff + pre-commit alongside test deps
ruff --version                   # >= 0.8, available on PATH
ruff check .                     # may report pre-existing violations (expected)
ruff format --check .            # may report unformatted files (expected)
pytest -v                        # full suite still green (config-only change)
```

**Commit:** `chore: configure ruff and add dev extras`

---

## Phase 2 — Apply ruff fixes and formatting across the tree

This is its own commit so the mechanical cleanup is reviewable in
isolation, separate from the tooling config in Phase 1 and the hook
wiring in Phase 3.

**Files:**
- Run `ruff check --fix .` and `ruff format .` from the repo root.
  Whatever files change, change.
- For any lint findings that ruff cannot autofix, address them
  manually. If a finding is genuinely incorrect (false positive),
  add a targeted `# noqa: <code>` comment with a one-line justification
  rather than disabling the rule globally.
- Do **not** modify behavior. Cosmetic changes only — formatting,
  import order, dead-import removal, deprecated-syntax modernization
  (`UP` rules). If a `B` (bugbear) finding suggests a real behavior
  change, leave it for a separate commit and add `# noqa: B...` here
  with a TODO referencing follow-up.

**Verification:**
```bash
ruff check .                     # exits 0 (no violations remaining)
ruff format --check .            # exits 0 (no formatting deltas)
pytest -v                        # full suite green — refactor preserved behavior
git diff --stat HEAD~1           # review scope of mechanical changes
```

**Commit:** `style: apply ruff lint and format across repo`

---

## Phase 3 — Add `.pre-commit-config.yaml` and install hooks

**Files:**
- ADD `.pre-commit-config.yaml` at the repo root:
  ```yaml
  repos:
    - repo: https://github.com/pre-commit/pre-commit-hooks
      rev: v5.0.0
      hooks:
        - id: trailing-whitespace
        - id: end-of-file-fixer
        - id: check-yaml
        - id: check-toml
        - id: check-json
        - id: check-merge-conflict
        - id: check-added-large-files

    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.8.0
      hooks:
        - id: ruff
          args: [--fix]
        - id: ruff-format

    - repo: https://github.com/compilerla/conventional-pre-commit
      rev: v3.6.0
      hooks:
        - id: conventional-pre-commit
          stages: [commit-msg]
          args:
            - feat
            - fix
            - docs
            - chore
            - refactor
            - test
            - ci
            - build

    - repo: local
      hooks:
        - id: pytest
          name: pytest (full suite)
          entry: pytest
          language: system
          pass_filenames: false
          always_run: true
          stages: [pre-commit]
  ```
- Install the hooks locally (one-time per clone — *not* a file change,
  but required for the hook wiring to take effect on the next commit):
  ```bash
  pre-commit install
  pre-commit install --hook-type commit-msg
  ```

**Verification:**
```bash
pre-commit run --all-files               # every hook passes; pytest runs the full suite
test -x .git/hooks/pre-commit            # exits 0
test -x .git/hooks/commit-msg            # exits 0

# Negative test for commit-msg validation:
git commit --allow-empty -m "not conventional"   # rejected by conventional-pre-commit
git commit --allow-empty -m "chore: smoke commit"  # accepted; running the full hook chain

# Roll back the smoke commit if you don't want to keep it:
git reset --soft HEAD~1
```

Note: `pre-commit run --all-files` will execute the pytest hook and
therefore needs Docker running locally (testcontainers requirement).
If Docker is not available in this phase, run `SKIP=pytest pre-commit
run --all-files` to verify the rest, then run pytest separately when
Docker is back.

**Commit:** `chore: configure pre-commit hooks for lint, format, tests, and conventional commits`

(This commit itself goes through the new hooks — first real validation.)

---

## Phase 4 — Document the workflow in `README.md`

**Files:**
- MODIFY `README.md`:
  - Add a new "Git hooks" section after the existing setup walkthrough,
    covering:
    - The 3 bootstrap commands:
      ```bash
      pip install -e ".[test,dev]"
      pre-commit install
      pre-commit install --hook-type commit-msg
      ```
    - One-line summary of what runs on commit (hygiene + ruff lint/fix
      + ruff format + full pytest suite) and on commit-msg
      (Conventional Commits validation against the eight types from
      `AGENTS.md`).
    - The two escape hatches: `git commit --no-verify` (skips
      everything) and `SKIP=pytest git commit -m "..."` (skips only
      the slow test hook).
    - A pointer to `https://pre-commit.com/` for further reference.
  - Cross-reference the existing "Tests" section so contributors
    understand the pytest hook reuses the same harness.

**Verification:**
- In a fresh shell, follow the new "Git hooks" section verbatim from
  a clean clone (or `rm -rf .venv && rm -f .git/hooks/pre-commit
  .git/hooks/commit-msg`). Both `pre-commit install` invocations
  succeed and the next test commit goes through the hooks.
- Run `pre-commit run --all-files` one more time — green.
- The commit for this phase itself exercises the hooks end-to-end
  (lint, format, pytest, commit-msg validation all run on the README
  edit).

**Commit:** `docs: document pre-commit hook setup in readme`

---

## Definition of done (after all 4 phases)

1. `pip install -e ".[test,dev]" && pre-commit install &&
   pre-commit install --hook-type commit-msg` is sufficient for a
   fresh contributor to be fully wired up.
2. Every `git commit` runs hygiene checks, ruff lint with autofix,
   ruff format, and the full pytest suite. Failure of any hook aborts
   the commit.
3. Every `git commit -m "..."` validates the message against the
   eight Conventional Commits types declared in `AGENTS.md`. Invalid
   messages are rejected and the message is preserved for retry.
4. `pre-commit run --all-files` exits 0 on `main`.
5. `git commit --no-verify` and `SKIP=pytest git commit ...` are
   documented escape hatches in the README.
6. The Phase 3 and Phase 4 commits themselves passed through the new
   hooks — proof that the wiring works end-to-end.

---

## Cross-cutting reminders

- All config files, README additions, and commit messages are written
  in English per `CLAUDE.md`.
- Conventional Commits: `chore:` for tooling and config changes,
  `style:` for the mechanical ruff sweep in Phase 2, `docs:` for the
  README addition.
- Phases 1 and 2 are committed *before* the hooks are installed, so
  they bypass the not-yet-existing pre-commit hook. Phase 3 onward is
  gated by the hooks themselves.
- The pytest hook uses `language: system` and therefore requires the
  contributor's `.venv` to have `pytest` + `testcontainers[postgres]`
  available. The bootstrap order in the README (`pip install -e
  ".[test,dev]"` *before* `pre-commit install`) ensures this.
- Do not introduce CI integration of pre-commit in this plan — that
  is listed as an open question in the spec and belongs in a separate
  iteration.
- Do not bump the existing `mcp-server/pyproject.toml` to add ruff
  configuration. The repo-root `pyproject.toml` is authoritative for
  tooling config that applies to the whole tree (mirrors how pytest
  config was consolidated there in the prior automated-tests work).
