#!/bin/sh
# Provision Omni's bundled services and stay foreground. See Dockerfile
# header for the known root/initdb issue.
set -e

omni install \
    --port "${API_PORT:-8882}" \
    ${OMNI_API_KEY:+--api-key "$OMNI_API_KEY"}

omni start

# Tail PM2 logs so PID 1 stays alive and logs surface in
# `docker compose logs omni`.
exec pm2 logs --raw
