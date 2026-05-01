#!/usr/bin/env bash
# Top-level orchestrator. Runs every install/configure step in order; aborts
# on the first failure. Each sub-script is itself idempotent, so re-running
# this on a partially-configured machine converges on the final state.
#
# When invoked as root (e.g. fresh VPS), bootstraps a dedicated non-root user
# (default: nutrition; override with APP_USER env var) and re-executes itself
# as that user. Genie's embedded Postgres refuses uid 0, so the install steps
# cannot run as root.

source "$(dirname "$0")/lib/common.sh"

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${APP_USER:-nutrition}"

bootstrap_app_user() {
    log "running as root — bootstrapping app user '$APP_USER'"

    if ! id "$APP_USER" >/dev/null 2>&1; then
        log "creating user: $APP_USER"
        useradd --create-home --shell /bin/bash "$APP_USER"
    else
        log "user $APP_USER already exists"
    fi

    if getent group docker >/dev/null 2>&1; then
        log "adding $APP_USER to docker group"
        usermod -aG docker "$APP_USER"
    else
        log "docker group not found — install-deps.sh will flag missing docker"
    fi

    log "chowning $REPO_ROOT to $APP_USER"
    chown -R "$APP_USER:$APP_USER" "$REPO_ROOT"

    # If $APP_USER can't traverse to the repo (typical when it lives under
    # /root/), relocate it to $APP_USER's home so the install steps can run.
    if ! su - "$APP_USER" -c "test -r '$SCRIPTS_DIR/setup.sh'"; then
        local app_home target
        app_home=$(getent passwd "$APP_USER" | cut -d: -f6)
        target="$app_home/$(basename "$REPO_ROOT")"
        if [ -e "$target" ]; then
            die "$APP_USER cannot reach $REPO_ROOT and $target already exists — resolve manually."
        fi
        log "relocating repo: $REPO_ROOT -> $target"
        mv "$REPO_ROOT" "$target"
        chown -R "$APP_USER:$APP_USER" "$target"
        SCRIPTS_DIR="$target/scripts"
    fi

    log "re-executing setup.sh as $APP_USER"
    exec su - "$APP_USER" -c "$SCRIPTS_DIR/setup.sh"
}

if [ "$(id -u)" -eq 0 ]; then
    bootstrap_app_user
fi

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
