# Pre-commit hooks — design

## Goal

Configure git hooks to run lint, format, and the test suite before every
commit, and validate that commit messages follow the
[Conventional Commits](https://www.conventionalcommits.org/) specification
mandated by `AGENTS.md`. The same hooks must be reproducible across
every contributor's machine — installable from a single config file,
checked into the repo.

The mechanism is the [`pre-commit`](https://pre-commit.com/) framework,
not Husky. The project is pure Python (no `package.json`, no Node
toolchain). `pre-commit` is the de-facto Python equivalent and integrates
directly with the existing tooling (`pyproject.toml`, `pytest`).

## Non-goals

- Running hooks in CI. CI already runs `pytest` via
  `.github/workflows/test.yml`. Adding a parallel lint job is a
  reasonable follow-up but is out of scope for this iteration (see
  Open questions).
- Auto-fixing every lint violation in the repo as part of this change.
  The hook will fix what `ruff --fix` and `ruff format` can fix on
  staged files; existing violations elsewhere in the tree are addressed
  separately.
- Replacing or modifying the existing pytest harness. The hook simply
  invokes `pytest` — same suite, same fixtures, same Postgres container.
- Pinning a Python version, adopting `pre-commit.ci`, or introducing
  any commit-signing / GPG flow.
- Interactive commit authoring (e.g. `cz commit`). The user chose
  `conventional-pre-commit` over `commitizen`; only validation is in
  scope.

## Architecture

### Repository layout after this change

```
conversational-ai-whatsapp-1/
├── .pre-commit-config.yaml     [NEW]
├── pyproject.toml              (edit: add [tool.ruff] + dev extras)
└── README.md                   (edit: add "Git hooks" section)
```

No new directories. No `package.json`. No Node dependency.

### `.pre-commit-config.yaml`

Single file, four `repos:` blocks:

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

Three points worth flagging:

1. **The pytest hook uses `language: system`**, not pre-commit's
   isolated venv. The test suite needs `testcontainers` + a working
   Docker socket, which only works in the contributor's already-set-up
   `.venv`. With `language: system`, pre-commit shells out to `pytest`
   from the active environment.
2. **`pass_filenames: false` + `always_run: true`** — pytest discovers
   its own tests, so the hook does not pass it the staged paths. The
   hook also runs even when no Python files changed, because a
   migration tweak or a config change can break the suite too.
3. **The Conventional Commits hook runs at `commit-msg` stage**, not
   `pre-commit`. Pre-commit and commit-msg are distinct git hook types
   with separate install commands (covered below).

### `pyproject.toml` additions

Add `[tool.ruff]` config and a `dev` optional-dependencies group:

```toml
[project.optional-dependencies]
test = [
    "pytest>=7.0",
    "testcontainers[postgres]>=4.0",
    "psycopg2-binary>=2.9.0",
]
dev = [
    "pre-commit>=3.7",
    "ruff>=0.8",
]

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

Notes:

- `target-version = "py311"` matches `requires-python = ">=3.11"`
  already declared above.
- `line-length = 100` is a middle ground between Black's 88 and the
  120 some teams use. Easy to tune later by editing one line.
- The `dev` extra includes `ruff` so contributors can run
  `ruff check` / `ruff format` directly from their shell, outside the
  hook. The hook itself uses the version pinned in
  `.pre-commit-config.yaml` (`ruff-pre-commit @ v0.8.0`); they should
  be kept in sync when bumped.

## Components

### Bootstrap workflow (one-time per clone)

```
pip install -e ".[test,dev]"
pre-commit install
pre-commit install --hook-type commit-msg
```

`pre-commit install` writes `.git/hooks/pre-commit`. The second invocation
writes `.git/hooks/commit-msg`. Both are required because git treats them
as separate hook types and `pre-commit install` only installs the
default `pre-commit` type.

After bootstrap, every `git commit` automatically runs:

1. **Hygiene checks** (whitespace, EOF, YAML/TOML/JSON syntax, merge
   markers, large files) — fast, no project deps required.
2. **Ruff lint with `--fix`** — autofixes safe violations on staged
   files; if anything cannot be autofixed, the commit aborts with an
   error.
3. **Ruff format** — formats staged files; reformatted files must be
   re-staged before retrying.
4. **Pytest, full suite** — runs `pytest` against the active env.
   Spins up the Postgres testcontainer for integration tests. Aborts
   the commit on any failure.
5. **Commit-msg validation** — the message must match the Conventional
   Commits format and use one of the eight allowed types from
   `AGENTS.md`. If not, the commit aborts and the message is preserved
   so the contributor can fix and retry.

### Escape hatches

Documented in the README for legitimate cases (WIP commits, urgent
fixes, hot debugging loops):

- **`git commit --no-verify`** — skips all hooks, including commit-msg
  validation. Use sparingly; CI will still catch test regressions on
  push.
- **`SKIP=pytest git commit -m "…"`** — runs lint, format, and
  commit-msg validation but skips only the slow pytest hook. Useful
  when iterating on docs or config and you know tests are unaffected.

### README addition

A new short "Git hooks" section under the existing setup steps. Covers:

- The 3 bootstrap commands above
- One-line summary of what runs on commit / commit-msg
- The two escape hatches
- A link to `https://pre-commit.com/` for further reference

No other README sections change.

## Migration plan

1. Create `.pre-commit-config.yaml` at the repo root with the contents
   in the Architecture section.
2. Edit `pyproject.toml`:
   a. Add the `dev` group under `[project.optional-dependencies]`.
   b. Add the `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]`
      blocks.
3. Reinstall the project to pick up the new extra:
   `pip install -e ".[test,dev]"`.
4. Run `pre-commit install` and
   `pre-commit install --hook-type commit-msg`.
5. Run `pre-commit run --all-files` once to surface and fix any
   pre-existing lint/format violations across the tree. Any auto-fixes
   are committed in a single dedicated commit (e.g.
   `chore: apply ruff lint and format across repo`). Anything that
   cannot be auto-fixed is addressed manually before the rollout.
6. Run the full pytest suite once via `pre-commit run pytest --all-files`
   to confirm the hook wiring works end-to-end (Docker available,
   testcontainers reachable, fixtures intact).
7. Edit `README.md` to add the "Git hooks" section.
8. Commit the configuration change(s) using a message that itself
   passes the new commit-msg hook (e.g.
   `chore: configure pre-commit hooks`).

## Risks and mitigations

- **Pytest in the pre-commit hook is slow** — every commit pays the
  Docker container startup cost (~3–5s for `postgres:16-alpine`) plus
  the suite runtime. The user explicitly accepted this tradeoff during
  brainstorming. The `SKIP=pytest` escape hatch is the documented
  release valve for tight iteration loops.
- **`language: system` couples the pytest hook to the contributor's
  active env** — if a contributor commits without first running
  `pip install -e ".[test,dev]"`, the hook will fail with an obscure
  "pytest: command not found". Mitigation: README is explicit about the
  bootstrap order, and the failure mode is loud and quick to diagnose.
- **Two `ruff` versions to keep in sync** — the one in
  `.pre-commit-config.yaml` (used by the hook) and the one in the
  `dev` extra (used directly from the shell). Mitigation: bump them
  together in one commit. `pre-commit autoupdate` handles the hook
  pin; the dev extra is a one-line edit.
- **Contributors who use `--no-verify` to bypass everything** — until
  CI also enforces lint, the hooks are advisory. Mitigation listed as
  a follow-up under Open questions.
- **`check-added-large-files` could flag a legitimate file** —
  default threshold is 500 KB. The repo's only large files today are
  `tmux-server-*.log` (~924 KB each) which are already covered by
  `.gitignore` (`tmux-*`) and therefore never reach the hook. New
  large files added intentionally will trigger it; if expected, the
  contributor can pass `--maxkb` or remove the file.

## Open questions

1. **Should CI also run `pre-commit run --all-files` as a separate
   job?** This would close the `--no-verify` gap and catch any
   contributor who edits in a tool that does not respect git hooks
   (some IDEs). Suggested as a follow-up after this change lands.
2. **Should `bandit` or another security linter be added?** Out of
   scope for this iteration. Easy to bolt on later as another
   `repos:` block.
