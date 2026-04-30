# Genie image — wraps automagik-genie from npm.
#
# Genie agents are loaded from `agents/<name>/AGENTS.md` (system prompt) and
# `agents/<name>/agent.yaml` (config). MCP wiring comes from `.mcp.json`.
# All three are bind-mounted at runtime so edits don't require a rebuild.
#
# Omni → Genie communication is via NATS (see `omni connect --help`), not
# HTTP. Genie subscribes to NATS topics for the agents Omni has connected.

FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates tmux git \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g automagik-genie@latest

WORKDIR /app

# The exact entrypoint that subscribes to NATS for Omni-driven messages is
# not yet confirmed — `genie --help` after this image is built will reveal
# the right subcommand. See docs/specs/2026-04-30-reproducible-setup-design.md §4.2.
CMD ["genie"]
