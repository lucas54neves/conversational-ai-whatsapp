#!/usr/bin/env bash
# Idempotently registers the nutrition agent with Genie's directory.
# Reads model and promptMode from agents/nutrition/agent.yaml so that file
# remains the single source of truth.

source "$(dirname "$0")/lib/common.sh"

require_non_root

cd "$REPO_ROOT"

command_exists genie || die "genie CLI not found. Run scripts/install-genie.sh first."
command_exists yq    || die "yq not found. Run scripts/install-deps.sh first."
command_exists jq    || die "jq not found. Run scripts/install-deps.sh first."

AGENT_YAML="agents/nutrition/agent.yaml"
[ -f "$AGENT_YAML" ] || die "$AGENT_YAML not found"

MODEL=$(yq -r .model "$AGENT_YAML")
PROMPT_MODE=$(yq -r .promptMode "$AGENT_YAML")

if [ -z "$MODEL" ] || [ "$MODEL" = "null" ]; then
    die "model missing from $AGENT_YAML"
fi
if [ -z "$PROMPT_MODE" ] || [ "$PROMPT_MODE" = "null" ]; then
    die "promptMode missing from $AGENT_YAML"
fi

if genie dir ls --json | jq -e '.[] | select(.name=="nutrition")' >/dev/null 2>&1; then
    log "nutrition already registered in genie dir, skipping"
    exit 0
fi

log "registering nutrition agent (model=$MODEL, prompt-mode=$PROMPT_MODE)"
genie dir add nutrition \
    --dir "$REPO_ROOT/agents/nutrition" \
    --model "$MODEL" \
    --prompt-mode "$PROMPT_MODE"

log "nutrition agent registered"
