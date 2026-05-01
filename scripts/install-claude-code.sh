#!/usr/bin/env bash
# Installs the Anthropic Claude Code CLI via the official installer if not present.

source "$(dirname "$0")/lib/common.sh"

if command_exists claude; then
    log "claude already installed: $(claude --version 2>/dev/null || echo present)"
    exit 0
fi

if ! command_exists curl; then
    die "curl is required to install Claude Code."
fi

log "installing claude-code via https://claude.ai/install.sh"
curl -fsSL https://claude.ai/install.sh | bash

prepend_path "$HOME/.local/bin"

if ! command_exists claude; then
    die "claude-code installation finished but 'claude' is not on PATH. Add ~/.local/bin to PATH and retry."
fi

log "claude installed: $(claude --version 2>/dev/null || echo present)"
