#!/usr/bin/env bash
# Register the nutrition agent with Omni so incoming WhatsApp messages
# route to Genie. Omni's agent integration is provider-based and uses
# the OpenAI chat-completions schema, so Genie must expose an
# OpenAI-compatible endpoint at the configured base URL.
#
# Steps:
#   1. Create an Omni provider pointing at the Genie service.
#   2. Look up the WhatsApp instance id (created when you pair).
#   3. Bind the provider to the instance.
#
# Re-running this script is safe: provider names are unique, so step 1
# fails idempotently if already created.

set -euo pipefail

PROVIDER_NAME="${PROVIDER_NAME:-nutrition-genie}"
GENIE_BASE_URL="${GENIE_BASE_URL:-http://genie:4000}"
OMNI_AGENT_API_KEY="${OMNI_AGENT_API_KEY:-genie-local}"

run_omni() {
    docker compose exec -T omni omni "$@"
}

echo "[register] creating provider ${PROVIDER_NAME} -> ${GENIE_BASE_URL}"
run_omni providers create \
    --name "${PROVIDER_NAME}" \
    --schema openai \
    --base-url "${GENIE_BASE_URL}" \
    --api-key "${OMNI_AGENT_API_KEY}" \
    || echo "[register] provider may already exist — continuing"

echo "[register] listing instances; pick the WhatsApp id you paired"
run_omni instances list

echo "[register] export INSTANCE_ID=<id> and re-run with --bind to attach the provider"

if [[ "${1:-}" == "--bind" ]]; then
    : "${INSTANCE_ID:?set INSTANCE_ID to the paired WhatsApp instance id}"
    echo "[register] binding instance ${INSTANCE_ID} -> provider ${PROVIDER_NAME}"
    run_omni instances update "${INSTANCE_ID}" --agent-provider "${PROVIDER_NAME}"
    echo "[register] done"
fi
