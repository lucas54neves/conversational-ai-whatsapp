# Conversational Nutrition Agent on WhatsApp

A Brazilian Portuguese nutrition assistant that runs on WhatsApp. Users log
meals in natural language and the agent tracks calories and macros against
daily targets calculated from a personal profile (Mifflin-St Jeor with
sedentary activity factor, adjusted by goal). All food data is sourced from
a local copy of the Brazilian TACO food composition table — no external
nutrition APIs at runtime.

The pipeline is:

```
WhatsApp ──► Omni (Baileys) ──► Genie (Claude Code) ──► MCP server ──► Postgres (TACO + meal logs)
```

## Architecture

The system is split across two planes:

- **Containerized data plane** — Postgres 16, a one-shot seeder that runs
  the schema migration and loads the TACO food table, and the Python MCP
  server. All three live in `docker-compose.yml`.
- **Host runtime plane** — Claude Code, Genie, and Omni run as
  host-installed binaries because they are not distributed as container
  images. Genie embeds its own Postgres on `127.0.0.1:19642` (separate from
  the project's database) and Omni keeps its state under `~/.omni`.

Cross-plane wiring: Genie reads the project's `.mcp.json` and connects to
the MCP server at `http://localhost:8000/sse`, which is the host-side port
exposed by the container.

The architectural rationale lives in
[`docs/specs/2026-04-30-dockerized-setup-design.md`](docs/specs/2026-04-30-dockerized-setup-design.md).

## Prerequisites

System packages on the host:

- Docker (with the `docker compose` plugin)
- Node.js 18+ **or** Bun
- `tmux`, `git`, `gh`, `jq`, `yq`, `curl`

Install hints:

| Tool   | Debian/Ubuntu                             | macOS (Homebrew)              |
|--------|-------------------------------------------|-------------------------------|
| docker | `sudo apt install -y docker.io`           | `brew install --cask docker`  |
| node   | `sudo apt install -y nodejs npm`          | `brew install node`           |
| bun    | `curl -fsSL https://bun.sh/install \| bash` | `brew install bun`         |
| tmux   | `sudo apt install -y tmux`                | `brew install tmux`           |
| gh     | see https://cli.github.com                | `brew install gh`             |
| jq     | `sudo apt install -y jq`                  | `brew install jq`             |
| yq     | `sudo snap install yq`                    | `brew install yq`             |

You also need an Anthropic API key **or** an active `claude login`
session. If you set `ANTHROPIC_API_KEY` in `.env`, Genie picks it up at
startup.

## Quick start

```bash
git clone <this repo> && cd conversational-ai-whatsapp-1
cp .env.example .env && "${EDITOR:-nano}" .env  # set POSTGRES_PASSWORD at minimum
./scripts/setup.sh                        # installs tools, brings up the stack, registers the agent
./scripts/pair-whatsapp.sh                # scans the QR with the WhatsApp app
```

After the QR scan, send a message to the paired number to start the
onboarding flow.

## What `setup.sh` does

`scripts/setup.sh` runs each step in order, aborting on the first failure.
Every step is itself idempotent, so re-running on a partially-configured
machine is safe.

1. `install-deps.sh` — verifies host packages.
2. `install-claude-code.sh` — installs the Claude Code CLI globally if
   missing.
3. `install-genie.sh` — runs Genie's official installer if `genie` is not
   on `PATH`.
4. `install-omni.sh` — runs Omni's official installer if `omni` is not on
   `PATH`.
5. `compose-up.sh` — `docker compose up -d --build`, then waits for the
   MCP server's TCP port.
6. `register-agent.sh` — adds the nutrition agent to Genie's directory,
   reading `model` and `promptMode` from `agents/nutrition/agent.yaml`.
7. `configure-omni.sh` — creates the WhatsApp instance, the Genie
   provider, the agent, and the route binding them.

Pairing is intentionally separate (`pair-whatsapp.sh`) because it requires
human interaction.

## Manual operation

Each script is also runnable on its own. They all source
`scripts/lib/common.sh`, which sets `set -euo pipefail` and loads `.env`.

- `scripts/install-deps.sh` — verifies host dependencies and prints
  install hints for any that are missing.
- `scripts/install-claude-code.sh` — installs the Claude Code CLI. No-op
  if `claude` is on `PATH`.
- `scripts/install-genie.sh` — installs Genie via its upstream
  installer. No-op if `genie` is on `PATH`.
- `scripts/install-omni.sh` — installs Omni via its upstream installer.
  No-op if `omni` is on `PATH`.
- `scripts/compose-up.sh` — brings up Postgres, the seeder, and the MCP
  server, then waits up to 60s for the MCP TCP port.
- `scripts/register-agent.sh` — registers the nutrition agent with
  Genie's directory. Detects an existing entry by name and skips.
- `scripts/configure-omni.sh` — creates four Omni resources (instance,
  provider, agent, route) idempotently.
- `scripts/pair-whatsapp.sh` — interactive. Detects existing pairing via
  `omni instances whoami` and confirms before logging out and re-pairing.
- `scripts/doctor.sh` — aggregated health check; prints
  "All systems go ✓" on full pass.
- `scripts/teardown.sh` — reverses the project state after explicit
  confirmation.

## Health check

`scripts/doctor.sh` runs the following in sequence:

- `genie doctor`
- `omni status`
- `docker compose ps`
- TCP probe to `localhost:8000`
- `omni providers test <id>` for the Genie provider

Each line is labelled `ok:` or `FAIL:`. The script exits 0 only when all
checks pass.

## Reset

`scripts/teardown.sh` confirms before doing anything, then:

- Deletes the Omni route, agent, provider, and instance for `nutrition`.
- Removes the `nutrition` entry from Genie's directory.
- Runs `docker compose down -v`, dropping the `pg_data` volume.

It does **not** uninstall Claude Code, Genie, or Omni globally. After
teardown, `./scripts/setup.sh` reproduces the original state.

## Tests

The Python test suite lives at the repo root under `tests/`, split
into `tests/unit/` (pure functions, no I/O) and `tests/integration/`
(Postgres-backed via [testcontainers](https://testcontainers.com/)).
The integration layer spins up `postgres:16-alpine` automatically and
tears it down at the end of the session — no `TEST_DATABASE_URL` to
export and nothing to start by hand.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[test]

pytest tests/unit/         # fast loop, no Docker
pytest tests/integration/  # spins up an ephemeral Postgres container
pytest                     # full suite
pytest -m "not integration"  # shorthand for unit-only
```

The integration layer needs a working Docker socket. If you can run
`docker compose` you are already set.

`.github/workflows/test.yml` runs the same `pytest -v` command on
every push and pull request via GitHub Actions.

## Troubleshooting

- **QR expired before scanning.** Re-run `./scripts/pair-whatsapp.sh`.
  The script confirms before logging out an active pairing.
- **`MCP server did not accept TCP on localhost:8000`.** Inspect
  `docker compose logs mcp-server`. The most common cause is a port
  conflict on 8000.
- **`omni providers test` fails.** Check `omni status` and
  `genie doctor`. Genie's embedded Postgres binds `127.0.0.1:19642`; if
  another process holds that port, set `GENIE_PG_PORT` before running
  `setup.sh` and restart Genie.
- **`db-seed` reports "already populated".** Not a failure. The seeder
  short-circuits when `taco_foods` already has rows.
- **`genie dir add` complains about an existing entry.** Already handled
  by `register-agent.sh`'s idempotency check; if you ran the command by
  hand, run `genie dir rm nutrition` first.
- **WhatsApp number banned.** Out of scope for this setup. Baileys uses
  an unofficial protocol; the only remedy is rotating numbers.

## Project layout

```
.
├── agents/nutrition/         # Genie agent definition + prompts
├── db/
│   ├── migrations/           # SQL schema
│   └── seed/                 # Dockerfile + seed.py + taco.csv (one-shot)
├── mcp-server/               # Python MCP server (Dockerfile + src + tests)
├── scripts/
│   ├── lib/common.sh         # shared bash helpers
│   ├── setup.sh              # top-level orchestrator
│   ├── teardown.sh           # reverses project state
│   ├── doctor.sh             # aggregated health check
│   ├── install-*.sh          # dependency / runtime bootstrappers
│   ├── compose-up.sh         # docker compose up + readiness wait
│   ├── register-agent.sh     # Genie directory registration
│   ├── configure-omni.sh     # Omni instance/provider/agent/route
│   └── pair-whatsapp.sh      # interactive WhatsApp QR pairing
├── docs/
│   ├── 2026-04-30-dockerized-setup-plan.md
│   └── specs/2026-04-30-dockerized-setup-design.md
├── docker-compose.yml
├── .env.example
└── .mcp.json
```

## Adapting to a different domain

The orchestration scripts are domain-agnostic. To swap the nutrition agent
for a different one:

1. Replace `agents/nutrition/` with your own agent directory and update
   `agent.yaml` (`model`, `promptMode`).
2. Replace `mcp-server/` with the MCP server that exposes your domain's
   tools, keeping the SSE endpoint at `http://localhost:8000/sse` (or
   update `.mcp.json`).
3. Replace `db/migrations/` and `db/seed/` with your schema and seed data.
4. Update the agent name (`nutrition`) in `register-agent.sh`,
   `configure-omni.sh`, `pair-whatsapp.sh`, and `teardown.sh` if you want
   a different identifier.

The `scripts/lib/common.sh` helpers, `docker-compose.yml` shape, and
overall flow stay the same.

## Architectural decisions

See [`docs/specs/2026-04-30-dockerized-setup-design.md`](docs/specs/2026-04-30-dockerized-setup-design.md)
for the full design rationale, including why Genie and Omni run on the
host instead of in containers.
