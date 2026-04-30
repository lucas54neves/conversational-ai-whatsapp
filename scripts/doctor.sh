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
    run_check "genie serve running"   bash -c 'genie serve status 2>&1 | grep -q "Status:.*running"'
    run_check "genie omni-bridge up"  bash -c 'genie serve status 2>&1 | grep -q "omni-bridge:.*running"'
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
    # Existence check only — `omni providers test` does an HTTP probe that does
    # not apply to nats-genie providers. Bridge liveness is covered by the
    # `genie omni-bridge up` check above.
    PROVIDER_ID=$(omni providers list --json | jq -r '.[] | select(.schema=="nats-genie") | .id // empty' | head -n1)
    if [ -z "$PROVIDER_ID" ]; then
        failures+=("omni nats-genie provider missing")
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
