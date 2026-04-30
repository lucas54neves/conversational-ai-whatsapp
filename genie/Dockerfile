# Genie image — wraps the @automagik/genie installer since no official
# image is published.
#
# Agent definitions (`agents/`), MCP wiring (`.mcp.json`), and the workspace
# config (`.genie/workspace.json`) are bind-mounted at runtime so edits
# reload without rebuilding this image. See compose for the mount points.
#
# The exact `genie` CLI surface (start flag, healthcheck path, port flag) is
# based on docs/specs/2026-04-29-nutrition-agent-design.md and needs to be
# verified against the upstream installer. See
# docs/specs/2026-04-30-reproducible-setup-design.md §4.2 and §8.

FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates tmux git \
    && rm -rf /var/lib/apt/lists/*

# Pin to a tagged release once one is confirmed upstream.
RUN curl -fsSL https://get.automagik.dev/genie | bash

WORKDIR /app

EXPOSE 4000

# Replace with the verified flag once confirmed against `genie --help`.
CMD ["genie", "start", "--port", "4000"]
