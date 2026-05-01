#!/usr/bin/env bash
# Shared helpers sourced by every script under scripts/.
# Sets strict mode, loads .env if present, exposes log/die/confirm/wait helpers.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

log() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

die() {
    printf '[%s] ERROR: %s\n' "$(date +%H:%M:%S)" "$*" >&2
    exit 1
}

confirm() {
    local prompt="${1:-Continue?}"
    local reply
    if [ ! -t 0 ]; then
        die "Confirmation required but no TTY available: $prompt"
    fi
    read -r -p "$prompt [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Genie's embedded pgserve refuses to start under uid 0 (Postgres won't run as
# root). Abort early with a clear message so users don't get a cryptic failure
# halfway through setup. Set GENIE_ALLOW_ROOT=1 to bypass.
require_non_root() {
    if [ "$(id -u)" -eq 0 ] && [ "${GENIE_ALLOW_ROOT:-0}" != "1" ]; then
        die "do not run as root: genie's embedded pgserve refuses uid 0. Re-run as a normal user (without sudo), or set GENIE_ALLOW_ROOT=1 to override."
    fi
}

# Prepend a directory to PATH if it exists and isn't already present. Exported
# so child processes (e.g. each run_step in setup.sh) inherit the update.
prepend_path() {
    local dir="$1"
    [ -d "$dir" ] || return 0
    case ":$PATH:" in
        *":$dir:"*) return 0 ;;
    esac
    export PATH="$dir:$PATH"
}

# Ensure user-local bin directories where setup-installed CLIs land are on PATH.
# The genie installer drops its binary in bun's global bin (or npm's, as a
# fallback), neither of which is exported by default in non-interactive shells.
ensure_user_bins_on_path() {
    prepend_path "${BUN_INSTALL:-$HOME/.bun}/bin"
    prepend_path "$HOME/.local/bin"
    if command_exists npm; then
        local npm_prefix
        npm_prefix=$(npm config get prefix 2>/dev/null || true)
        [ -n "$npm_prefix" ] && prepend_path "$npm_prefix/bin"
    fi
}

ensure_user_bins_on_path

wait_for_tcp() {
    local host="$1"
    local port="$2"
    local timeout="${3:-30}"
    local elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; then
            exec 3<&-
            exec 3>&-
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}
