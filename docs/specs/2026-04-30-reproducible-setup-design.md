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

**Base image:** `oven/bun:1` — Omni is a Bun/Node CLI.

**Build steps (`omni/Dockerfile`):**
1. Install `curl` and `ca-certificates`.
2. `bun add -g @automagik/omni`.
3. Copy `entrypoint.sh` to `/usr/local/bin/omni-entrypoint`.

`omni install` is run **at startup** (idempotent, non-interactive — confirmed
via `omni install --help`), not at image build, because the API key comes
from the environment at runtime.

**Runtime:**
- Entrypoint script runs `omni install --port $API_PORT --api-key $OMNI_API_KEY`,
  then `omni start` (which provisions PM2-managed Postgres, NATS, and API),
  then `pm2 logs` to keep PID 1 alive.
- Exposed ports: `8882` (API), `4222` (NATS — needed by Genie).
- Volumes: `omni_data:/root/.omni` — pgserve datadir, NATS state, Baileys
  session. One volume keeps everything together since Omni manages all
  three internally.
- Environment:
  - `API_PORT` (default `8882`).
  - `OMNI_API_KEY` — explicit key so the smoke test and admin calls work.
- Genie integration uses NATS (`omni connect <instance-id> <agent-name>`),
  not HTTP. Genie subscribes to topics matching the agent name in its
  workspace's `agents/` directory.

**Pairing flow:**
1. `docker compose exec omni omni channels add --type whatsapp` creates an
   instance.
2. `docker compose exec omni omni instances list` returns its id.
3. `docker compose exec omni omni instances qr <id> --watch` shows the QR.
4. `docker compose exec omni omni connect <id> nutrition` wires it to the
   `agents/nutrition/` agent loaded by Genie.

### 4.2 `genie`

**Base image:** `node:20-slim`.

**Build steps (`genie/Dockerfile`):**
1. Install `ca-certificates`, `tmux`, `git`. `tmux` is required because
   `.genie/workspace.json` declares a `tmux.socket`.
2. `npm install -g automagik-genie@latest` (the canonical install per
   the npm registry; the legacy `curl https://get.automagik.dev/genie | bash`
   path returns 404 in the current host).
3. No agent files are baked in — `agents/`, `.mcp.json`, and
   `.genie/workspace.json` are bind-mounted at runtime.

**Runtime:**
- Entrypoint: `genie` with no args. Per `genie --help`, this "starts
  Genie server (Forge + MCP)".
- Volumes:
  - `./agents:/app/agents` — agent definitions; writable so Genie can update
    its directory if needed.
  - `./.genie:/app/.genie` — workspace config; writable for the same reason.
  - `./.mcp.json:/app/.mcp.json:ro`
  - `genie_state:/var/lib/genie` — sessions, memory.
- Environment:
  - `ANTHROPIC_API_KEY` — required.
  - `MCP_SERVER_URL=http://mcp-server:8000/sse`.
  - `NATS_URL=nats://omni:4222` — for the `omni connect` integration.
- `depends_on`: `omni` (started, for NATS), `mcp-server` (started).

**Open questions to verify before merging:**
- Exact mechanism by which Genie subscribes to NATS topics for a given
  agent name (after `omni connect <instance-id> <agent-name>`). The
  integration is implied by `omni connect --help` ("Connect an Omni
  instance to a Genie agent via NATS") but Genie's own CLI does not
  document a NATS subscriber subcommand explicitly. May happen
  automatically when both are running with shared workspace conventions.
- Whether Genie auto-loads `.mcp.json` from the workspace root or
  needs explicit configuration.

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

| Risk | Status | Mitigation |
|------|--------|------------|
| **Omni pgserve refuses root** | **Open** | `initdb` (postgres binary used by Omni's bundled pgserve) bails out when run as root; the bun image runs as root by default. `--database-url` saves an external URL into Omni's config but the API still tries to spawn pgserve at boot and crashloops. Workarounds attempted: switching to non-root broke `bun add -g` linking under `/usr/local`. Open paths: (a) run Omni on the host as the original nutrition spec prescribed, (b) custom non-root image with bun installs landing under the user's home, (c) confirm with upstream whether there is a flag to fully disable pgserve. |
| **Genie NATS subscription mechanism** | **Open** | `omni connect <instance> <agent>` documents a NATS-based handoff to Genie, but Genie's CLI does not expose an explicit NATS-subscriber subcommand. Likely automatic when Genie's `agents/<name>/` matches and both share NATS, but unverified. |
| `omni install` is interactive in build context | Resolved | Confirmed non-interactive — installer prints "[deprecated] silent no-op". |
| PM2 inside Docker masks crashes | Mitigated | Entrypoint runs `pm2 logs --raw` so crashes surface in container stdout. |
| Baileys QR appears only on first run, lost in detached logs | Mitigated | `omni instances qr <id> --watch` streams the QR on demand via the script. |
| Genie installer pulls a moving target | Mitigated | Switched to `npm install -g automagik-genie@latest` (the legacy `get.automagik.dev/genie` curl path 404s). |
| Two Postgres instances confuse reviewers | N/A | Omni manages its bundled pgserve internally; only one Postgres is exposed in compose (the nutrition one on 5432). |
| WhatsApp session lost on `docker compose down -v` | Mitigated | `teardown.sh` requires `--purge` for `-v`. |

---

## 9. Out-of-Scope Follow-ups

- Replace Omni's bundled Postgres with the existing `postgres` service. Saves
  one container; requires confirming Omni supports an external DB.
- Replace embedded NATS with a sibling `nats` service for the same reason.
- Add a `Makefile` wrapping the scripts: `make up`, `make pair`, `make test`.
- CI step that builds the full compose and runs `smoke-test.sh` against it.
- Pin Genie and Omni installs to specific version tags once upstream
  publishes stable release tags.
