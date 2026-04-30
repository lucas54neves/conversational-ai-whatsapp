# Dockerized Setup — Implementation Plan

**Date:** 2026-04-30
**Source design:** [`docs/specs/2026-04-30-dockerized-setup-design.md`](specs/2026-04-30-dockerized-setup-design.md)
**Scope:** Step-by-step execution order to deliver the dockerized setup
described in the design spec. Each phase is one commit, follows
Conventional Commits per `CLAUDE.md`, and ends with explicit verification
commands so it can be validated in isolation.

---

## Phase 1 — Preparatory cleanup

**Files:**
- DELETE `db/init/01-create-omni-db.sql`
- DELETE `db/init/` (now empty)
- MODIFY `.env.example` — replace contents per design §8
- ADD `.gitignore` at repo root with at least:
  `.env`, `.DS_Store`, `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`,
  `pg_data/`

**Verification:**
- `git status` shows `db/init/` deleted and `.env.example` modified
- `cat .env.example` matches design §8

**Commit:** `chore: remove obsolete omni db init and rationalize env`

---

## Phase 2 — `docker-compose.yml`

**Files:**
- ADD `docker-compose.yml` at repo root — exact YAML from design §5
- ADD `.dockerignore` at repo root:
  `.env`, `.git`, `**/__pycache__`, `**/.pytest_cache`, `node_modules`,
  `pg_data`
- Healthcheck for `mcp-server` is defined in compose (not in the
  Dockerfile), keeping the image generic. Use:
  ```yaml
  healthcheck:
    test:
      - CMD
      - python
      - -c
      - "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',8000))"
    interval: 5s
    timeout: 3s
    retries: 10
  ```

**Verification:**
```bash
docker compose config                              # YAML valid
cp .env.example .env && sed -i 's/change-me/devpw/' .env
docker compose up -d --build
docker compose ps                                  # postgres healthy, db-seed exited 0, mcp-server healthy
curl -fsS http://localhost:8000/sse                # SSE handshake responds
docker compose logs db-seed | grep "Seeded"        # TACO populated
docker compose down                                # volume preserved
```

**Commit:** `feat(compose): orchestrate postgres, seeder, and mcp server`

---

## Phase 3 — Shared library and dependency scripts

**Files:**
- ADD `scripts/lib/common.sh`:
  - `set -euo pipefail`
  - Sources `.env` via `set -a; source .env; set +a` (only if file exists)
  - Helpers: `log`, `die`, `confirm`, `command_exists`, `wait_for_tcp`
    (using bash's `/dev/tcp/<host>/<port>` pseudo-device)
- ADD `scripts/install-deps.sh`:
  - For each of `docker`, `node|bun`, `tmux`, `git`, `gh`, `jq`, `yq`,
    `curl`: run `command_exists`; on missing, print install hint
    (apt/brew) and fail.
- ADD `scripts/install-claude-code.sh`:
  - `if ! command_exists claude; then npm install -g @anthropic-ai/claude-code; fi`
- ADD `scripts/install-genie.sh`:
  - `if ! command_exists genie; then curl -fsSL https://raw.githubusercontent.com/automagik-dev/genie/main/install.sh | bash; fi`
- ADD `scripts/install-omni.sh`:
  - Analogous, fetching the official Omni install script.

**Verification:**
```bash
chmod +x scripts/*.sh scripts/lib/*.sh
./scripts/install-deps.sh                          # passes (deps present) or names what is missing
./scripts/install-claude-code.sh                   # skip-if-present
./scripts/install-genie.sh && genie doctor          # functional
./scripts/install-omni.sh && omni status            # functional
```

**Commit:** `feat(scripts): add host dependency verifiers and tool bootstrappers`

---

## Phase 4 — Compose orchestration and idempotent registration

**Files:**
- ADD `scripts/compose-up.sh`:
  - `docker compose up -d --build`
  - `wait_for_tcp localhost 8000 60` and log "MCP server ready"
- ADD `scripts/register-agent.sh`:
  - Read `model` and `promptMode` from `agents/nutrition/agent.yaml`
    using `yq -r`.
  - Idempotency check:
    `genie dir ls --json | jq -e '.[] | select(.name=="nutrition")'`
  - On miss:
    `genie dir add nutrition --dir "$(pwd)/agents/nutrition" --model <m> --prompt-mode <p>`
- ADD `scripts/configure-omni.sh` — four list-then-create blocks per
  design §6:
  1. WhatsApp Baileys instance named `nutrition`
  2. Provider with `--schema genie`
  3. Agent named `nutrition` linked to the Genie provider with
     `--provider-agent-id nutrition`
  4. Route binding the instance to the agent

**Verification:**
```bash
./scripts/compose-up.sh                            # logs "MCP server ready"
./scripts/register-agent.sh && genie dir ls | grep nutrition
./scripts/configure-omni.sh
omni instances list  | grep nutrition
omni providers list  | grep -i genie
omni agents list     | grep nutrition
omni routes list                                   # contains the binding
# Idempotency
./scripts/configure-omni.sh                        # all four steps say "skipping"
./scripts/register-agent.sh                        # says "already registered"
```

**Commit:** `feat(scripts): add compose orchestrator and idempotent agent/Omni configuration`

---

## Phase 5 — Pairing, doctor, teardown

**Files:**
- ADD `scripts/pair-whatsapp.sh`:
  - Resolve `INSTANCE_ID` by name from `omni instances list --json`
  - If `omni instances whoami <id>` returns a phone, prompt
    `confirm "Re-pair?"`; if yes, run `omni instances logout <id>` first
  - `omni instances qr <id>` in foreground (waits for scan)
- ADD `scripts/doctor.sh`:
  - Run in sequence and aggregate exit codes:
    `genie doctor`, `omni status`, `docker compose ps`,
    `wait_for_tcp localhost 8000 5`, `omni providers test <id>`
  - Print `All systems go ✓` on full pass; list failures otherwise
- ADD `scripts/teardown.sh`:
  - `confirm "This will destroy local nutrition data. Continue?"`
  - Reverse-order delete, each step tolerating "not found":
    routes → agents → providers → instances → `genie dir rm nutrition` →
    `docker compose down -v`
  - Never uninstalls Genie/Omni/Claude Code globally

**Verification:**
```bash
./scripts/doctor.sh                                # all green
./scripts/teardown.sh                              # confirms then cleans
docker volume ls   | grep pg_data    && exit 1 || echo OK   # volume gone
genie dir ls       | grep nutrition  && exit 1 || echo OK
omni instances list | grep nutrition && exit 1 || echo OK
# Pair re-flow
./scripts/setup.sh && ./scripts/pair-whatsapp.sh   # full cycle
```

**Commit:** `feat(scripts): add interactive WhatsApp pairing, doctor, and teardown`

---

## Phase 6 — Top-level orchestrator

**Files:**
- ADD `scripts/setup.sh` — calls in order, aborting on first failure
  (`set -e` inherited from `lib/common.sh`):
  ```
  install-deps  →  install-claude-code  →  install-genie  →  install-omni
            →  compose-up  →  register-agent  →  configure-omni
            →  echo "Now run: ./scripts/pair-whatsapp.sh"
  ```

**Verification:**
```bash
./scripts/teardown.sh                               # reset state
./scripts/setup.sh                                  # full setup, end-to-end
./scripts/setup.sh                                  # re-run: every step skips, exit 0
./scripts/doctor.sh                                 # all green
./scripts/pair-whatsapp.sh                          # pair and send a test message
```

**Commit:** `feat(scripts): add top-level setup orchestrator`

---

## Phase 7 — README rewrite

**Files:**
- MODIFY `README.md` per design §9. Sections in order: introduction +
  pipeline diagram, Architecture, Prerequisites, Quick start, What
  `setup.sh` does, Manual operation, Health check, Reset, Troubleshooting,
  Project layout, Adapting to a different domain, Architectural
  decisions.

**Verification:**
- Manual link check for every relative path mentioned (`scripts/...`,
  `docs/specs/...`).
- Run the Quick start verbatim in a temporary directory and confirm it
  reaches a paired WhatsApp number.
- Confirm every script under `/scripts` has a paragraph in
  "Manual operation".

**Commit:** `docs: rewrite README with full setup walkthrough and troubleshooting`

---

## Definition of done (after all 7 phases)

1. On a machine with system dependencies installed,
   `git clone && cp .env.example .env && ./scripts/setup.sh && ./scripts/pair-whatsapp.sh`
   reaches a paired WhatsApp number.
2. A test message to the paired number triggers the agent's onboarding
   flow (Genie → MCP → Postgres → reply on WhatsApp).
3. Re-running `./scripts/setup.sh` is a loud no-op (every step skips with
   an explicit message) and exits 0.
4. `./scripts/teardown.sh` followed by `./scripts/setup.sh` reproduces the
   state from item 1.
5. `./scripts/doctor.sh` returns exit 0 and prints "All systems go ✓".
6. The README guides a fresh evaluator to item 1 without consulting any
   other file in the repository.

---

## Cross-cutting reminders

- Every script starts with `#!/usr/bin/env bash` and `source "$(dirname
  "$0")/lib/common.sh"` (or `lib/../lib/common.sh` for files at
  `scripts/`).
- Every script must be `chmod +x`.
- Logs use the `log` helper so output is consistent and timestamped.
- All commit messages and file contents are written in English per
  `CLAUDE.md`.
- The `pair-whatsapp.sh` script is the only one that requires a TTY; all
  others must run in non-interactive environments (CI smoke tests are a
  potential follow-up).
