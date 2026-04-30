#!/usr/bin/env bash
# Installs the Anthropic Claude Code CLI globally via npm if not present.

source "$(dirname "$0")/lib/common.sh"

if command_exists claude; then
    log "claude already installed: $(claude --version 2>/dev/null || echo present)"
    exit 0
fi

if ! command_exists npm; then
    die "npm is required to install Claude Code. Install Node.js first."
fi

log "installing @anthropic-ai/claude-code globally"
npm install -g @anthropic-ai/claude-code

log "claude installed: $(claude --version 2>/dev/null || echo present)"
