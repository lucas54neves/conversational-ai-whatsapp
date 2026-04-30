# Design: Reproducible Setup with Containerized Omni

**Date:** 2026-04-30
**Topic:** End-to-end reproducible bring-up via `docker compose up`
**Related:** `docs/specs/2026-04-29-nutrition-agent-design.md`
**Status:** Draft

---

## 1. Motivation

Mandatory requirements #1, #3, and #7 of `docs/technical-test.md` demand a working
WhatsApp ↔ Omni ↔ Genie ↔ MCP pipeline plus a README with reproducible setup
instructions. The current state:

- `docker-compose.yml` only covers `postgres`, `seed`, `mcp-server`.
- Omni is documented only as host-side prose in the nutrition design doc.
- Genie is documented only as a host-side `curl | bash` install.
- `README.md` is empty (0 bytes) despite a misleading commit message.
- No `scripts/` directory, no `Makefile`, no smoke test.

A reviewer cannot run the agent without translating prose into commands
and reverse-engineering port and `agent_url` wiring. The path from
`git clone` to "answers on WhatsApp" must be one command plus a one-time QR scan.

---

## 2. Goals and Non-Goals

### Goals
- `cp .env.example .env && docker compose up -d` brings the full pipeline online.
- The Baileys WhatsApp session persists across container restarts (one-time pair).
- `scripts/smoke-test.sh` proves end-to-end delivery without a manual chat.
- `README.md` documents quickstart, pair-WhatsApp, verify, and troubleshoot flows.
- Genie's MCP wiring (`.mcp.json` + `agents/nutrition/`) loads automatically.

### Non-Goals
- Production hardening: TLS termination, secret rotation, hardened images.
- Kubernetes manifests, multi-tenant deployment, horizontal scaling.
- CI pipelines.

---

## 3. Target Topology

```
┌──────────────────────────────────────────────────────────────┐
│ docker compose                                               │
│                                                              │
│   omni                  genie               mcp-server       │
│   :8882 (API)           :4000 (sse)         :8000 (sse)      │
│   embedded pg :8432     state vol            │               │
│   embedded nats :4222    │                   │               │
│   baileys session vol    │                   ▼               │
│        │                 │                postgres :5432     │
│        └── AGENT_URL ────┘                (nutrition data)   │
│                                              ▲               │
│                                              │               │
│                                            seed              │
└──────────────────────────────────────────────────────────────┘
                            ▲
                            │ Baileys / WhatsApp Web
                            ▼
                       WhatsApp users
```

`postgres`, `seed`, and `mcp-server` exist and stay structurally unchanged.
`omni` and `genie` are added in this iteration.

---

## 4. Service Specifications

### 4.1 `omni`

**Base image:** `oven/bun:1` — Omni is a Bun/Node CLI per the nutrition design doc.

**Build steps (`omni/Dockerfile`):**
1. Install OS deps required by Omni's bundled Postgres/NATS (`curl`, `ca-certificates`, libpq).
2. `bun add -g @automagik/omni`.
3. `omni install` at image build so PM2 services are pre-registered.
   If the installer is interactive, feed answers via `expect` or use a
   non-interactive flag once one is confirmed against Omni's CLI.

**Runtime:**
- Entrypoint: `omni start` in the foreground so PID 1 forwards SIGTERM.
  If `omni start` does not stay in foreground, wrap with `pm2-runtime`.
- Exposed ports: `8882` (API). NATS (`4222`) and embedded Postgres (`8432`)
  are container-internal.
- Volumes:
  - `omni_pg_data:/var/lib/omni/postgres` — Omni's bundled Postgres datadir.
  - `omni_sessions:/var/lib/omni/sessions` — Baileys session and credentials.
- Healthcheck: `curl -fsS http://localhost:8882/health` (path **TBD**, verify).
- Environment:
  - `AGENT_URL=http://genie:4000` — where Omni forwards messages.
- `depends_on`: `genie` (started). Omni will retry on connection refusal,
  so a strict healthy gate is not required.

**Open questions to verify before merging:**
- Exact env var names Omni reads (`AGENT_URL` is a guess).
- Whether `omni install` is non-interactive in a build context.
- How Baileys QR is surfaced (logs, file, HTTP endpoint).
- Whether Omni's bundled Postgres can be replaced by an external one.

### 4.2 `genie`

**Base image:** `node:20-slim`. Genie's installer expects a recent glibc and
Node-style tooling; a Debian-slim base is the smallest reliable target.

**Build steps (`genie/Dockerfile`):**
1. Install `curl`, `ca-certificates`, `tmux`, `git`. `tmux` is required because
   `.genie/workspace.json` declares a `tmux.socket`.
2. `curl -fsSL https://get.automagik.dev/genie | bash`. Pin to a tag once
   one is confirmed against the upstream installer.
3. No agent files are baked in — `agents/`, `.mcp.json`, and
   `.genie/workspace.json` are bind-mounted read-only at runtime so edits
   reload without rebuilding the image.

**Runtime:**
- Entrypoint: `genie start --port 4000` (exact flag **TBD**, verify against
  Genie's CLI). The process must stay in the foreground.
- Exposed ports: `4000` — internal only; only `omni` calls it.
- Volumes:
  - `./agents:/app/agents:ro`
  - `./.genie:/app/.genie:ro`
  - `./.mcp.json:/app/.mcp.json:ro`
  - `genie_state:/var/lib/genie` — sessions, memory, conversation state.
- Healthcheck: `curl -fsS http://localhost:4000/health` (path **TBD**).
- Environment:
  - `ANTHROPIC_API_KEY` — required.
  - `MCP_SERVER_URL=http://mcp-server:8000/sse` — overrides the host in `.mcp.json`.
- `depends_on`: `mcp-server` (healthy).

**Open questions to verify before merging:**
- Exact `genie` CLI flags for headless / port-bound start.
- Whether Genie expects a writable workspace dir (current mount is read-only).
- How session state is partitioned per user — confirm `phone_number` propagates
  through Omni → Genie as the session key.

### 4.3 Unchanged services

- `postgres` — nutrition data only. No change.
- `seed` — one-shot migration + TACO import. Add `restart: "no"` if missing.
- `mcp-server` — add a healthcheck (`curl -fsS http://localhost:8000/sse` or a
  dedicated health route) so future `genie` can wait on it.

### 4.4 Compose-level concerns

- Default network: service name = DNS hostname.
- `depends_on` chain: `seed → mcp-server → genie → omni`.
- Single `.env` file; secrets via `env_file:`, never inlined.
- `restart: unless-stopped` on long-running services; none on `seed`.

---

## 5. Setup Scripts (next iteration)

```
scripts/
├── setup.sh              copy .env.example → .env, prompt for missing values
├── pair-whatsapp.sh      surface Baileys QR from omni logs / session dir
├── register-agent.sh     POST agent definition to Omni API (idempotent)
├── smoke-test.sh         send test message via Omni API, assert response shape
└── teardown.sh           docker compose down (-v requires an explicit flag)
```

Each script must:
- Be idempotent.
- Use `set -euo pipefail`.
- Print one progress line per step.
- Exit non-zero on the first failure.

`register-agent.sh` replaces the manual `omni config set agent_url` from the
original prose by calling Omni's API or writing its config file directly.

---

## 6. README Structure (next iteration)

In order:

1. Title + one-paragraph description — what the agent does, on what channel.
2. Prerequisites — Docker 24+, Compose v2, Anthropic API key, spare WhatsApp number.
3. Quickstart — three commands: clone, `./scripts/setup.sh`, `docker compose up -d`.
4. Pairing WhatsApp — `./scripts/pair-whatsapp.sh`, scan QR, done.
5. Verify — `./scripts/smoke-test.sh` expected output.
6. Architecture — link to both spec docs.
7. Configuration reference — every `.env` variable, what it does, default.
8. Troubleshooting — port conflicts, token expiry re-pair, postgres init failures.
9. WhatsApp number for evaluators — placeholder until live.

---

## 7. Verification Plan

A reviewer running the project from scratch must be able to:

1. Clone the repo, run `./scripts/setup.sh`, run `docker compose up -d`.
2. Run `./scripts/pair-whatsapp.sh`, scan QR with the throwaway WhatsApp.
3. Run `./scripts/smoke-test.sh` and see a green check.
4. Send "oi" from a phone and receive the onboarding prompt.

Each step must complete in under five minutes on a fresh machine with Docker only.

---

## 8. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `omni install` is interactive in build context | `expect` script in Dockerfile, or pin to a non-interactive flag confirmed against Omni CLI |
| PM2 inside Docker masks crashes | Use `pm2-runtime` (forwards exit codes) instead of `pm2 start` |
| Baileys QR appears only on first run, lost in detached logs | `pair-whatsapp.sh` reads from a known log file or session dir |
| Genie installer pulls a moving target | Pin to a specific version tag in the install command |
| Two Postgres instances confuse reviewers | README labels them: "nutrition data" vs. "Omni internal" |
| WhatsApp session lost on `docker compose down -v` | `teardown.sh` requires explicit `--purge` flag for `-v` |
| Omni env var names are guesses | Verify against Omni docs; replace placeholders before merge |

---

## 9. Out-of-Scope Follow-ups

- Replace Omni's bundled Postgres with the existing `postgres` service. Saves
  one container; requires confirming Omni supports an external DB.
- Replace embedded NATS with a sibling `nats` service for the same reason.
- Add a `Makefile` wrapping the scripts: `make up`, `make pair`, `make test`.
- CI step that builds the full compose and runs `smoke-test.sh` against it.
- Pin Genie and Omni installs to specific version tags once upstream
  publishes stable release tags.
