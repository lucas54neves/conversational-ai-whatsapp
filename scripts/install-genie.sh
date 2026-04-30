#!/usr/bin/env bash
# Installs the Genie CLI via the official upstream installer if not present.

source "$(dirname "$0")/lib/common.sh"

if command_exists genie; then
    log "genie already installed: $(genie --version 2>/dev/null || echo present)"
    exit 0
fi

log "installing genie via upstream installer"
curl -fsSL https://raw.githubusercontent.com/automagik-dev/genie/main/install.sh | bash

# The upstream installer drops genie in bun's global bin (or npm's). Those dirs
# may have been created during this step, so refresh PATH before re-checking.
ensure_user_bins_on_path

if ! command_exists genie; then
    die "genie installer ran but 'genie' is not on PATH. Open a new shell or update PATH."
fi

log "genie installed: $(genie --version 2>/dev/null || echo present)"
