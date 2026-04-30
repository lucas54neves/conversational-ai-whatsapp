# Dockerized Setup for the Conversational Nutrition Agent

**Date:** 2026-04-30
**Status:** Approved (design); pending implementation
**Scope:** End-to-end reusable setup that brings the existing nutrition agent
to a working WhatsApp endpoint on a fresh machine, using a containerized
data plane and host-installed Genie/Omni runtimes.

---

## 1. Context

The repository already implements the agent itself: a Python MCP server
(`mcp-server/`), a Genie agent definition (`agents/nutrition/`), and a
Postgres schema with TACO seed data (`db/`). What is missing is the glue
that makes the project bootable end-to-end on a new machine: a
`docker-compose.yml`, an installation/configuration flow that reaches a
paired WhatsApp number, and documentation that walks an evaluator (or any
future reuser) through the process.

The official upstream tools — Genie and Omni — are not distributed as
container images. Genie embeds its own Postgres (pgserve on port 19642)
and depends on host-side runtimes (Node/Bun, tmux, Claude Code CLI). Omni
ships as a CLI-driven multi-component runtime with its own state
directory. Both expose `curl ... | bash` bootstrappers.

Given those constraints, this design splits the system across two planes:

- **Containerized:** project-specific data + tools (Postgres, schema seed,
  MCP server).
- **Host:** Genie and Omni runtimes, installed via their official
  bootstrappers and wired up by shell scripts in `/scripts`.

## 2. Goals

1. A new contributor or evaluator can clone the repo and reach a paired
   WhatsApp number with two commands:
   `./scripts/setup.sh` followed by `./scripts/pair-whatsapp.sh`.
2. Every install/configuration step lives in a shell script under
   `/scripts`, so it is auditable, reusable, and re-runnable.
3. Re-running `setup.sh` on a partially-configured machine converges on the
   final state without errors or duplicates.
4. `teardown.sh` reverts the project's state on the host without affecting
   global Genie/Omni installations or unrelated projects.
5. The `README.md` documents prerequisites, the quick start, the role of
   each script, troubleshooting, and how to adapt the template to a
   different domain.

## 3. Non-goals

- Running Genie or Omni inside Docker. Their official distribution model
  is host-side; replicating it inside containers is out of scope.
- Auto-installing host system dependencies (apt/brew/etc.). Scripts only
  verify these and instruct the user; cross-distribution package management
  is fragile and not the project's responsibility.
- Production hardening (TLS, auth proxying, secrets management). The
  setup targets local development and evaluation.
- Integration tests that drive a real WhatsApp pairing. The pairing step
  is fundamentally interactive.

## 4. Architecture

```
┌─────────────────────────── HOST ─────────────────────────────┐
│                                                              │
│  Claude Code CLI ──► Genie CLI (tmux + pgserve:19642)        │
│        ▲                  ▲                                  │
│        │                  │ provider: genie                  │
│        │                  │                                  │
│  WhatsApp ──► Omni CLI/REST API + NATS + Baileys (~/.omni)   │
│                           │                                  │
│                           │ MCP SSE @ http://localhost:8000  │
│                           ▼                                  │
└──────────────── docker compose network ─────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        postgres:16    mcp-server     db-seed (one-shot)
        (volume:       (port 8000)    runs migrations + TACO,
         pg_data)                     exits 0; depends_on: pg
```

### Process layout

| Component        | Plane     | Lifecycle                       | State location                 |
|------------------|-----------|---------------------------------|--------------------------------|
| Postgres         | container | `docker compose up -d`          | named volume `pg_data`         |
| db-seed          | container | one-shot, `restart: "no"`       | none (reads project files)     |
| mcp-server       | container | long-running                    | none (reads Postgres)          |
| Claude Code CLI  | host      | npm-installed binary            | `~/.claude`                    |
| Genie            | host      | `genie` binary + tmux + pgserve | `~/.genie`                     |
| Omni             | host      | `omni` binary + REST + NATS     | `~/.omni`                      |

### Cross-plane wiring

- The MCP server in the container exposes port `8000` to the host, so
  Genie (on the host) can read `.mcp.json` at the project root and reach
  `http://localhost:8000/sse` literally.
- `.mcp.json` is committed and unchanged; no environment-specific URL
  needs to be templated.
- Genie embeds its own Postgres on `127.0.0.1:19642`; it does **not** share
  the project's Postgres. Omni manages its own state under `~/.omni`.
  Therefore the project's Postgres is dedicated to the nutrition data
  (`taco_foods`, `users`, `meal_logs`).

## 5. `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  db-seed:
    build: ./db/seed
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"

  mcp-server:
    build: ./mcp-server
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      PORT: 8000
    depends_on:
      postgres:
        condition: service_healthy
      db-seed:
        condition: service_completed_successfully
    ports:
      - "8000:8000"
    restart: unless-stopped

volumes:
  pg_data:
```

### Notes

- `pg_data` is a named volume. `docker compose down` preserves it;
  `docker compose down -v` drops it.
- `db-seed` is a one-shot service. Re-running `compose up` re-creates the
  container and re-runs the script, which is itself idempotent: the
  migration uses `IF NOT EXISTS` and the seed checks `SELECT COUNT(*) FROM
  taco_foods` before inserting.
- `service_completed_successfully` ensures `mcp-server` only starts after
  the schema and data are ready.
- The `mcp-server` healthcheck is a TCP probe issued from inside the
  container. The base image is `python:3.11-slim`, which lacks `nc`; the
  probe will be a one-liner using Python's `socket` module
  (`python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',8000))"`).
  Promoting to an HTTP `/health` endpoint requires a small change to
  `nutrition_tools/server.py` and is left for a follow-up.

## 6. `/scripts` layout

```
scripts/
├── lib/
│   └── common.sh
│
├── setup.sh
├── teardown.sh
├── doctor.sh
│
├── install-deps.sh
├── install-claude-code.sh
├── install-genie.sh
├── install-omni.sh
│
├── compose-up.sh
├── register-agent.sh
├── configure-omni.sh
└── pair-whatsapp.sh
```

### Responsibilities

| Script                    | Responsibility                                                                              |
|---------------------------|---------------------------------------------------------------------------------------------|
| `lib/common.sh`           | Sets `set -euo pipefail`, sources `.env`, exposes helpers: `log`, `die`, `confirm`, `command_exists`, `wait_for_url`, `wait_for_tcp`. Sourced by every script. |
| `setup.sh`                | Orchestrator. Calls the install/compose/configuration scripts in order. Skips finished steps. Does not pair WhatsApp. |
| `install-deps.sh`         | Verifies host dependencies (`docker`, `node`/`bun`, `tmux`, `git`, `gh`, `jq`, `yq`, `curl`). Fails with an actionable message if any is missing. |
| `install-claude-code.sh`  | If `claude` is not on `PATH`, runs `npm install -g @anthropic-ai/claude-code`. |
| `install-genie.sh`        | If `genie` is not on `PATH`, runs Genie's official `curl -fsSL .../install.sh \| bash`. |
| `install-omni.sh`         | If `omni` is not on `PATH`, runs Omni's official `curl -fsSL .../install.sh \| bash`. |
| `compose-up.sh`           | Runs `docker compose up -d --build`, then waits up to ~60s for the MCP server SSE port to accept TCP. |
| `register-agent.sh`       | Adds the nutrition agent to Genie's directory: `genie dir add nutrition --dir ./agents/nutrition --model "$(yq -r .model agents/nutrition/agent.yaml)" --prompt-mode "$(yq -r .promptMode agents/nutrition/agent.yaml)"`. Reading values from `agent.yaml` keeps the file as the single source of truth. Idempotent: `genie dir ls --json` is queried first; if `nutrition` is already present, the step is skipped. |
| `configure-omni.sh`       | Creates four Omni resources idempotently in this order: WhatsApp Baileys instance, Genie provider, agent linked to Genie, route binding instance to agent. Each step uses `omni <noun> list --json \| jq` to detect prior creation and capture IDs. |
| `pair-whatsapp.sh`        | Looks up the instance ID, prints a QR via `omni instances qr <id>`, and waits for the user to scan. Detects already-paired state via `omni instances whoami` and confirms before re-pairing. |
| `teardown.sh`             | Reverses the project state in the inverse order: Omni route → agent → provider → instance, then `genie dir rm nutrition`, then `docker compose down -v` (after explicit confirmation). Never uninstalls Genie/Omni/Claude Code globally. |
| `doctor.sh`               | Runs `genie doctor`, `omni status`, `docker compose ps`, a TCP probe to `localhost:8000`, and `omni providers test <id>`. Summarizes pass/fail. |

### `setup.sh` order

```
install-deps
  └─► install-claude-code
        └─► install-genie
              └─► install-omni
                    └─► compose-up
                          └─► register-agent
                                └─► configure-omni
                                      └─► (prints next step: pair-whatsapp.sh)
```

### Idempotency pattern (representative)

```bash
# scripts/configure-omni.sh
INSTANCE_ID=$(omni instances list --json | jq -r '.[] | select(.name=="nutrition") | .id // empty')
if [ -z "$INSTANCE_ID" ]; then
    INSTANCE_ID=$(omni instances create --channel whatsapp-baileys --name nutrition --json | jq -r .id)
    log "Created Omni instance $INSTANCE_ID"
else
    log "Omni instance already exists ($INSTANCE_ID), skipping"
fi
```

The same list-then-create pattern repeats for `omni providers`, `omni
agents`, and `omni routes`.

## 7. Idempotency invariants

- Re-running `setup.sh` from any partial state converges on the configured
  state without errors or duplicates.
- Re-running `setup.sh` after `teardown.sh` is equivalent to running it on
  a fresh machine.
- Any failed step aborts `setup.sh` (`set -euo pipefail`), prints a
  diagnostic, and leaves earlier successful steps intact for the next run.
- `pair-whatsapp.sh` is the only script with required human interaction.
  It is safe to re-run: if already paired, it confirms before re-pairing
  (which calls `omni instances logout` first).

## 8. Environment variables

A single `.env` file at the repository root, loaded automatically by
`docker compose` and explicitly via `set -a; source .env; set +a` in
`lib/common.sh`.

`.env.example`:

```bash
POSTGRES_USER=nutrition
POSTGRES_PASSWORD=change-me
POSTGRES_DB=nutrition

# Optional. Only set if your environment does not already provide it
# (e.g. you have not run `claude login`). Genie picks this up at startup.
# ANTHROPIC_API_KEY=
```

### Removed from the previous `.env.example`

- `OMNI_API_KEY` — unused. Omni's auth (`omni keys create`) is not part
  of this flow; the scripts drive Omni via its local CLI.
- `MCP_SERVER_URL` — unused. The MCP URL is hardcoded in `.mcp.json` at
  `http://localhost:8000/sse`, which Genie reads directly.

`.gitignore` includes `.env`. `.env.example` is committed.

## 9. `README.md` structure

```
# Conversational Nutrition Agent on WhatsApp

[existing intro paragraph + pipeline diagram]

## Architecture
  Brief recap: host vs. containerized split, why Genie/Omni live on the host.

## Prerequisites
  System dependencies (Docker, Node 18+/Bun, tmux, git, gh, jq, yq, curl)
  plus Linux/macOS install hints. Anthropic API key OR `claude login`
  session.

## Quick start
  git clone … && cd …
  cp .env.example .env && $EDITOR .env
  ./scripts/setup.sh
  ./scripts/pair-whatsapp.sh

## What `setup.sh` does
  Step list mirroring section 6 of this spec.

## Manual operation
  Per-script paragraph: when to run, prerequisites, post-conditions,
  verification.

## Health check
  ./scripts/doctor.sh — what each line means.

## Reset
  ./scripts/teardown.sh — what it removes vs. preserves.

## Troubleshooting
  QR expired, MCP server unreachable, agent-not-found, WhatsApp ban
  (out of scope), seed reports "already populated" (not a failure).

## Project layout
  Annotated tree of top-level directories.

## Adapting to a different domain
  How to swap the agent definition, MCP server, and schema while keeping
  the orchestration scripts.

## Architectural decisions
  Pointer to docs/specs/2026-04-30-dockerized-setup-design.md.
```

The README is in English (per `CLAUDE.md`). The agent's behavior
documentation stays in `agents/nutrition/AGENTS.md` and is not duplicated
in the README.

## 10. File changes

### New
```
docker-compose.yml
.dockerignore
.gitignore (or amended if it exists)

scripts/lib/common.sh
scripts/setup.sh
scripts/teardown.sh
scripts/doctor.sh
scripts/install-deps.sh
scripts/install-claude-code.sh
scripts/install-genie.sh
scripts/install-omni.sh
scripts/compose-up.sh
scripts/register-agent.sh
scripts/configure-omni.sh
scripts/pair-whatsapp.sh

docs/specs/2026-04-30-dockerized-setup-design.md  (this file)
```

### Modified
```
README.md       # rewrite per section 9
.env.example    # reduce per section 8
```

### Removed
```
db/init/01-create-omni-db.sql
db/init/                         # directory removed once empty
```

### Untouched
```
.mcp.json
mcp-server/Dockerfile
mcp-server/src/**, mcp-server/tests/**
mcp-server/pyproject.toml
db/seed/Dockerfile
db/seed/seed.py
db/seed/taco.csv
db/migrations/001_init.sql
agents/nutrition/agent.yaml
agents/nutrition/AGENTS.md
CLAUDE.md, AGENTS.md
```

## 11. Known limitations and follow-ups

- **MCP healthcheck is a TCP probe.** Promoting it to an HTTP `/health`
  endpoint requires a small server change and is deferred.
- **Omni ↔ Genie transport.** The official docs identify `--schema genie`
  as a supported provider type but do not detail the wire protocol. The
  scripts trust Omni's defaults; if a future Omni version requires extra
  fields (`--base-url`, `--api-key`), `configure-omni.sh` will need an
  update.
- **WhatsApp ban risk.** Baileys uses an unofficial WhatsApp protocol; if
  the paired number is banned by Meta, the only remedy is rotating
  numbers. Not addressable by this setup.
- **Genie embedded Postgres port collision.** Genie binds `127.0.0.1:19642`
  by default. If another process holds that port, the user must set
  `GENIE_PG_PORT` before running `setup.sh`. Documented in
  Troubleshooting.
- **Single-host assumption.** The design assumes Genie/Omni and the
  containers run on the same host (so `localhost:8000` resolves). A
  multi-host deployment is out of scope.
- **No CI integration.** The scripts are designed to run cleanly
  non-interactively up to the pairing step, which makes future CI smoke
  tests feasible, but no CI workflow is included in this spec.
