#!/usr/bin/env bash
# First-time setup. Copies .env.example to .env when missing, then prompts
# for required values that are still empty. Idempotent.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env"
EXAMPLE_FILE=".env.example"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "[setup] creating $ENV_FILE from $EXAMPLE_FILE"
    cp "$EXAMPLE_FILE" "$ENV_FILE"
else
    echo "[setup] $ENV_FILE already exists, leaving it alone"
fi

prompt_if_empty() {
    local key="$1"
    local current
    current=$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2- || true)
    if [[ -z "$current" ]]; then
        read -r -p "[setup] enter ${key}: " value
        if grep -qE "^${key}=" "$ENV_FILE"; then
            sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            rm -f "${ENV_FILE}.bak"
        else
            echo "${key}=${value}" >> "$ENV_FILE"
        fi
    else
        echo "[setup] ${key} already set"
    fi
}

prompt_if_empty ANTHROPIC_API_KEY
prompt_if_empty POSTGRES_PASSWORD
prompt_if_empty OMNI_API_KEY

echo "[setup] done — next: docker compose up -d"
