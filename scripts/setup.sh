#!/usr/bin/env bash
# Top-level orchestrator. Runs every install/configure step in order; aborts
# on the first failure. Each sub-script is itself idempotent, so re-running
# this on a partially-configured machine converges on the final state.

source "$(dirname "$0")/lib/common.sh"

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

run_step() {
    local script="$1"
    log "==> $script"
    bash "$SCRIPTS_DIR/$script"
}

run_step install-deps.sh
run_step install-claude-code.sh
run_step install-genie.sh
run_step install-omni.sh
run_step compose-up.sh
run_step register-agent.sh
run_step configure-omni.sh

log "setup complete"
log "Next: ./scripts/pair-whatsapp.sh"
