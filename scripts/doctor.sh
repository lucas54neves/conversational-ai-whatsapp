#!/usr/bin/env bash
# Aggregated health check across host runtimes and the docker compose stack.

source "$(dirname "$0")/lib/common.sh"

cd "$REPO_ROOT"

failures=()

run_check() {
    local label="$1"
    shift
    log "checking: $label"
    if "$@"; then
        log "  ok: $label"
    else
        log "  FAIL: $label"
        failures+=("$label")
    fi
}

if command_exists genie; then
    run_check "genie doctor"          genie doctor
else
    failures+=("genie not installed")
fi

if command_exists omni; then
    run_check "omni status"           omni status
else
    failures+=("omni not installed")
fi

run_check "docker compose ps"         docker compose ps
run_check "MCP TCP probe (localhost:8000)" wait_for_tcp localhost 8000 5

if command_exists omni && command_exists jq; then
    PROVIDER_ID=$(omni providers list --json | jq -r '.[] | select(.schema=="genie" or .name=="genie") | .id // empty' | head -n1)
    if [ -n "$PROVIDER_ID" ]; then
        run_check "omni providers test $PROVIDER_ID" omni providers test "$PROVIDER_ID"
    else
        failures+=("omni genie provider missing")
    fi
fi

if [ "${#failures[@]}" -eq 0 ]; then
    log "All systems go ✓"
    exit 0
fi

log "Failures:"
for f in "${failures[@]}"; do
    log "  - $f"
done
exit 1
