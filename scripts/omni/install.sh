#!/usr/bin/env bash
set -euo pipefail

curl -fsSL https://raw.githubusercontent.com/automagik-dev/omni/main/install.sh | bash -s -- --cli

export BUN_INSTALL="${HOME}/.bun"
export PATH="${BUN_INSTALL}/bin:${PATH}"

bun add -g pm2
