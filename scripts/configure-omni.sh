#!/usr/bin/env bash
# Idempotently wires WhatsApp -> nutrition agent in Omni:
#   1. ensure a whatsapp-baileys instance named "nutrition" exists
#   2. ensure that instance is connected to the genie agent "nutrition"
#      (creates the NATS Genie provider, agent record, and binding)

source "$(dirname "$0")/lib/common.sh"

command_exists omni || die "omni CLI not found. Run scripts/install-omni.sh first."
command_exists jq   || die "jq not found. Run scripts/install-deps.sh first."

AGENT_NAME="nutrition"

# 1. WhatsApp Baileys instance
INSTANCE_ID=$(omni instances list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id' | head -n1)
if [ -z "$INSTANCE_ID" ]; then
    omni instances create --channel whatsapp-baileys --name "$AGENT_NAME" --json >/dev/null
    INSTANCE_ID=$(omni instances list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id' | head -n1)
    [ -n "$INSTANCE_ID" ] || die "instance create succeeded but $AGENT_NAME not found in subsequent list"
    log "created omni instance $INSTANCE_ID"
else
    log "omni instance already exists ($INSTANCE_ID), skipping"
fi

# 2. Connect instance to genie agent (provider + agent record + binding in one call)
LINKED_AGENT_ID=$(omni instances list --json | jq -r --arg id "$INSTANCE_ID" '.[] | select(.id==$id) | .agentId // empty')
if [ -z "$LINKED_AGENT_ID" ]; then
    omni connect "$INSTANCE_ID" "$AGENT_NAME"
    log "connected instance $INSTANCE_ID to genie agent $AGENT_NAME"
else
    log "instance $INSTANCE_ID already linked to agent $LINKED_AGENT_ID, skipping"
fi

log "omni configuration complete"
