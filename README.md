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

## Prerequisites

- Docker 24+ and Docker Compose v2.
- An Anthropic API key.
- A spare WhatsApp account to pair with the agent. Baileys uses WhatsApp Web
  sessions; the same number cannot also be active on WhatsApp Web elsewhere.

## Quickstart

```bash
git clone git@github.com:lucas54neves/conversational-ai-whatsapp.git
cd conversational-ai-whatsapp
./scripts/setup.sh        # creates .env, prompts for API key + db password
docker compose up -d      # builds and starts postgres, mcp-server, genie, omni
```

The first `up` runs `db/seed/seed.py` once to apply migrations and import the
TACO dataset. Subsequent runs skip seeding.

## Pair WhatsApp

```bash
# 1. Create a WhatsApp instance inside Omni (one-time)
docker compose exec omni omni channels add whatsapp-baileys

# 2. Capture the instance id
docker compose exec omni omni instances list

# 3. Stream the pairing QR — scan with the throwaway WhatsApp account
INSTANCE_ID=<id-from-step-2> ./scripts/pair-whatsapp.sh

# 4. Connect the WhatsApp instance to the nutrition agent over NATS
INSTANCE_ID=<id> ./scripts/register-agent.sh --connect
```

The session lives in the `omni_data` volume, so pairing is a one-time
step unless the volume is wiped.

## Verify

```bash
./scripts/smoke-test.sh
```

Expected: a non-empty response from Omni and a `[smoke] PASS` line. If a
device is paired, sending "oi" from any WhatsApp should return the
onboarding prompt asking for weight, height, age, sex, and goal.

## Architecture

Two design specs cover the system:

- **Agent design** — [`docs/specs/2026-04-29-nutrition-agent-design.md`](docs/specs/2026-04-29-nutrition-agent-design.md).
  Domain model, MCP tools, conversation flows, database schema, error handling.
- **Setup design** — [`docs/specs/2026-04-30-reproducible-setup-design.md`](docs/specs/2026-04-30-reproducible-setup-design.md).
  Container topology, service contracts, scripts, risks, and items that still
  need to be verified against upstream Omni and Genie.

The MCP server exposes six tools to Genie: `search_food`, `save_user_profile`,
`get_user_profile`, `save_meal`, `get_daily_summary`, `get_weekly_history`.
Implementation lives in `mcp-server/src/nutrition_tools/`.

## Configuration

All configuration is in `.env`. `scripts/setup.sh` creates the file and
prompts for required values; the rest have safe defaults.

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Used by Genie to call Claude. Required. | — |
| `POSTGRES_PASSWORD` | Password for the nutrition Postgres instance. Required. | — |
| `MCP_SERVER_URL` | URL host-side tools use to reach the MCP server. Compose overrides this for the `genie` container with the in-network DNS name. | `http://localhost:8000` |
| `OMNI_URL` | Base URL the helper scripts use to reach Omni. | `http://localhost:8882` |
| `TEST_PHONE` | Phone number `smoke-test.sh` uses as the recipient. | `5511999999999` |
| `TEST_MESSAGE` | Body `smoke-test.sh` sends. | `ping` |

## Troubleshooting

**Port already in use (5432, 8000, 8882).** Another local Postgres, MCP, or
Omni is already bound. Stop it or remap the port in `docker-compose.yml`.

**Re-pair WhatsApp after a long offline period.** WhatsApp expires Web
sessions after extended inactivity. Wipe Omni's data volume with
`docker volume rm conversational-ai-whatsapp_omni_data` (this also clears
any Omni-side state like instances and providers), bring the stack back
up, and re-create the WhatsApp instance + pair. The nutrition database
is in a separate volume and is preserved.

**Postgres init failure on first boot.** Usually a leftover `postgres_data`
volume from a previous run with a different password. Run
`./scripts/teardown.sh --purge` and start over (this also wipes meal logs).

**Genie can't reach the MCP server.** Check `docker compose logs mcp-server`
for crash stacks; check `docker compose ps` to confirm `mcp-server` is
healthy. From inside the `genie` container,
`curl http://mcp-server:8000/sse` should respond.

**Omni `omni-api` PM2 process keeps restarting with `initdb cannot be run
as root`.** Omni's bundled Postgres (pgserve) refuses to run as root, and
the `bun` image runs as root by default. This is a known open issue —
see `omni/Dockerfile` header and
`docs/specs/2026-04-30-reproducible-setup-design.md` §8. As a workaround,
run Omni on the host instead of in compose: `bun add -g @automagik/omni`,
`omni install`, then point the host-installed Omni at this stack.

**`scripts/register-agent.sh` or `smoke-test.sh` returns 404.** Their API
paths (`/api/v1/agents`, `/api/v1/messages`) are placeholders that need to
be confirmed against Omni's actual API surface. Update the `OMNI_*_PATH`
constants at the top of each script.

## WhatsApp number for evaluators

_TBD — will be filled in once the agent is paired against a stable number._
