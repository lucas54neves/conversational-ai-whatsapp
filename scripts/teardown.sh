#!/usr/bin/env bash
# Stop the compose stack. Pass --purge to also remove volumes (this wipes
# the WhatsApp session and the nutrition database; you will need to pair
# WhatsApp again on the next start).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--purge" ]]; then
    echo "[teardown] stopping compose and removing volumes"
    docker compose down -v
else
    echo "[teardown] stopping compose (volumes preserved)"
    echo "[teardown] use --purge to wipe data and the WhatsApp session"
    docker compose down
fi
