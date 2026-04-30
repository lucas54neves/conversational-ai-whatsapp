#!/usr/bin/env bash
# Wire WhatsApp messages from Omni to the Genie nutrition agent via NATS.
# Omni's CLI exposes `omni connect <instance-id> <agent-name>` for this;
# the connection is bidirectional once the instance is paired and Genie
# is running with the matching agent in its directory.
#
# Steps:
#   1. List Omni instances; pick the WhatsApp instance you paired.
#   2. Export INSTANCE_ID=<id>.
#   3. Re-run with --connect.

set -euo pipefail

AGENT_NAME="${AGENT_NAME:-nutrition}"

run_omni() {
    docker compose exec -T omni omni "$@"
}

if [[ "${1:-}" != "--connect" ]]; then
    echo "[register] listing Omni instances:"
    run_omni instances list
    echo "[register] export INSTANCE_ID=<id> and re-run: $0 --connect"
    exit 0
fi

: "${INSTANCE_ID:?set INSTANCE_ID to the paired WhatsApp instance id}"

echo "[register] connecting instance ${INSTANCE_ID} -> agent ${AGENT_NAME}"
run_omni connect "${INSTANCE_ID}" "${AGENT_NAME}"
echo "[register] done"
