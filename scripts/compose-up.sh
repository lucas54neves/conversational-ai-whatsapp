#!/usr/bin/env bash
# Brings up the docker compose stack and waits for the MCP server's TCP port.

source "$(dirname "$0")/lib/common.sh"

cd "$REPO_ROOT"

if [ ! -f .env ]; then
    die ".env not found at repo root. Copy .env.example and edit it before running this."
fi

log "docker compose up -d --build"
docker compose up -d --build

log "waiting for MCP server on localhost:8000 (up to 60s)"
if wait_for_tcp localhost 8000 60; then
    log "MCP server ready"
else
    docker compose ps >&2 || true
    die "MCP server did not accept TCP on localhost:8000 within 60s"
fi
