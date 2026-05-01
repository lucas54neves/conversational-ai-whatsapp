#!/usr/bin/env bash
# Interactive script that pairs a WhatsApp number with the nutrition Omni
# instance. If already paired, asks whether to re-pair (logout + new QR).

source "$(dirname "$0")/lib/common.sh"

# Omni's auth state lives under $HOME/.omni, populated by configure-omni.sh as
# the app user during setup. If a fresh-VPS user runs this from their root
# shell after setup.sh's bootstrap, omni would talk to the server with no/stale
# credentials and fail with "Invalid API key". Re-exec as the app user so the
# README's documented flow works without manual `su`.
APP_USER="${APP_USER:-nutrition}"
if [ "$(id -u)" -eq 0 ]; then
    id "$APP_USER" >/dev/null 2>&1 || die "running as root and user '$APP_USER' does not exist; run scripts/setup.sh first."
    log "running as root — re-executing as $APP_USER"
    exec su - "$APP_USER" -c "cd '$REPO_ROOT' && exec ./scripts/pair-whatsapp.sh"
fi

command_exists omni || die "omni CLI not found. Run scripts/install-omni.sh first."
command_exists jq   || die "jq not found. Run scripts/install-deps.sh first."

AGENT_NAME="nutrition"

INSTANCE_ID=$(omni instances list --json | jq -r --arg n "$AGENT_NAME" '.[] | select(.name==$n) | .id // empty')
if [ -z "$INSTANCE_ID" ]; then
    die "omni instance '$AGENT_NAME' not found. Run scripts/configure-omni.sh first."
fi

PHONE=$(omni instances whoami "$INSTANCE_ID" 2>/dev/null | jq -r '.phone // empty' 2>/dev/null || true)

if [ -n "$PHONE" ] && [ "$PHONE" != "null" ]; then
    log "instance $INSTANCE_ID is already paired to $PHONE"
    if confirm "Re-pair?"; then
        log "logging out current session"
        omni instances logout "$INSTANCE_ID"
    else
        log "keeping existing pairing, exiting"
        exit 0
    fi
fi

log "opening WhatsApp QR (scan from the WhatsApp app: Linked Devices)"
omni instances connect --force-new-qr "$INSTANCE_ID"
omni instances qr "$INSTANCE_ID"
