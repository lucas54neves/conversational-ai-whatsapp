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
