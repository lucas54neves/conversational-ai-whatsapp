#!/usr/bin/env bash
# Pair WhatsApp by streaming the QR from Omni. After the first run you
# need to know your instance id — list them with:
#
#     docker compose exec omni omni instances list
#
# Then export INSTANCE_ID=<id> and re-run this script.
#
# Already-paired sessions persist in the omni_sessions volume; re-running
# is harmless.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! docker compose ps --services --status running | grep -q '^omni$'; then
    echo "[pair] omni is not running — start it with 'docker compose up -d' first" >&2
    exit 1
fi

if [[ -z "${INSTANCE_ID:-}" ]]; then
    echo "[pair] INSTANCE_ID is not set."
    echo "[pair] listing existing instances; create one with:"
    echo "[pair]   docker compose exec -T omni sh -lc 'export PATH=/home/omni/.local/bin:/home/omni/.bun/bin:\$PATH; omni channels add whatsapp-baileys'"
    docker compose exec -T omni sh -lc 'export PATH=/home/omni/.local/bin:/home/omni/.bun/bin:$PATH; omni instances list'
    echo "[pair] export INSTANCE_ID=<id> and re-run this script"
    exit 0
fi

echo "[pair] streaming QR for instance ${INSTANCE_ID} — scan with WhatsApp"
docker compose exec -T omni sh -lc "export PATH=/home/omni/.local/bin:/home/omni/.bun/bin:\$PATH; omni instances qr \"${INSTANCE_ID}\""
