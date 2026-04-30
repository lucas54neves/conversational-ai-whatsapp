#!/usr/bin/env bash
# Reverses the project state on the host. Removes Omni resources, the Genie
# directory entry, and the docker compose stack with its volume. Never
# uninstalls Genie/Omni/Claude Code globally.

source "$(dirname "$0")/lib/common.sh"

cd "$REPO_ROOT"

if ! confirm "This will destroy local nutrition data. Continue?"; then
    log "aborted"
    exit 0
fi

AGENT_NAME="nutrition"

# Best-effort delete: every step tolerates "not found".
safe() { "$@" || log "  (ignored failure: $*)"; }

if command_exists omni && command_exists jq; then
    INSTANCE_ID=$(omni instances list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id // empty' | head -n1)
    PROVIDER_ID=$(omni providers list --json | jq -r --arg n "nats-genie-$AGENT_NAME" '.[] | select(.schema=="nats-genie" and .name==$n) | .id // empty' | head -n1)
    # Active agents named "$AGENT_NAME" (soft-deleted records have active=="no" and can be left alone).
    AGENT_IDS=$(omni agents list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n and .active=="yes") | .id')

    # Delete the instance first so its FK to the agent is released.
    if [ -n "$INSTANCE_ID" ]; then
        log "deleting omni instance $INSTANCE_ID"
        safe omni instances delete "$INSTANCE_ID"
    fi
    for AGENT_ID in $AGENT_IDS; do
        log "deleting omni agent $AGENT_ID"
        safe omni agents delete "$AGENT_ID"
    done
    if [ -n "$PROVIDER_ID" ]; then
        log "deleting omni provider $PROVIDER_ID"
        safe omni providers delete "$PROVIDER_ID"
    fi
fi

if command_exists genie; then
    log "removing nutrition from genie dir"
    safe genie dir rm "$AGENT_NAME"
fi

log "docker compose down -v"
safe docker compose down -v

log "teardown complete"
