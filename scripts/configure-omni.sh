#!/usr/bin/env bash
# Idempotently creates the Omni resources needed to route WhatsApp messages
# to the nutrition agent: instance -> provider -> agent -> route.

source "$(dirname "$0")/lib/common.sh"

command_exists omni || die "omni CLI not found. Run scripts/install-omni.sh first."
command_exists jq   || die "jq not found. Run scripts/install-deps.sh first."

AGENT_NAME="nutrition"
PROVIDER_NAME="genie"

# 1. WhatsApp Baileys instance
INSTANCE_ID=$(omni instances list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id // empty')
if [ -z "$INSTANCE_ID" ]; then
    INSTANCE_ID=$(omni instances create \
        --channel whatsapp-baileys \
        --name "$AGENT_NAME" \
        --json | jq -r .id)
    log "created omni instance $INSTANCE_ID"
else
    log "omni instance already exists ($INSTANCE_ID), skipping"
fi

# 2. Genie provider
PROVIDER_ID=$(omni providers list --json | jq -r --arg n "$PROVIDER_NAME" '.[] | select(.name==$n or .schema=="genie") | .id // empty' | head -n1)
if [ -z "$PROVIDER_ID" ]; then
    PROVIDER_ID=$(omni providers create \
        --schema genie \
        --name "$PROVIDER_NAME" \
        --json | jq -r .id)
    log "created omni provider $PROVIDER_ID"
else
    log "omni provider already exists ($PROVIDER_ID), skipping"
fi

# 3. Agent linked to the Genie provider
AGENT_ID=$(omni agents list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id // empty')
if [ -z "$AGENT_ID" ]; then
    AGENT_ID=$(omni agents create \
        --name "$AGENT_NAME" \
        --provider-id "$PROVIDER_ID" \
        --provider-agent-id "$AGENT_NAME" \
        --json | jq -r .id)
    log "created omni agent $AGENT_ID"
else
    log "omni agent already exists ($AGENT_ID), skipping"
fi

# 4. Route binding instance -> agent
ROUTE_ID=$(omni routes list --json | jq -r --arg i "$INSTANCE_ID" --arg a "$AGENT_ID" '.[] | select(.instance_id==$i and .agent_id==$a) | .id // empty')
if [ -z "$ROUTE_ID" ]; then
    ROUTE_ID=$(omni routes create \
        --instance-id "$INSTANCE_ID" \
        --agent-id "$AGENT_ID" \
        --json | jq -r .id)
    log "created omni route $ROUTE_ID"
else
    log "omni route already exists ($ROUTE_ID), skipping"
fi

log "omni configuration complete"
