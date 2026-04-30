#!/usr/bin/env bash
# Installs the Omni CLI via the official upstream installer if not present.

source "$(dirname "$0")/lib/common.sh"

if command_exists omni; then
    log "omni already installed: $(omni --version 2>/dev/null || echo present)"
    exit 0
fi

log "installing omni via upstream installer"
curl -fsSL https://raw.githubusercontent.com/automagik-dev/omni/main/install.sh | bash

if ! command_exists omni; then
    die "omni installer ran but 'omni' is not on PATH. Open a new shell or update PATH."
fi

log "omni installed: $(omni --version 2>/dev/null || echo present)"
