#!/usr/bin/env bash
# Verify that required host dependencies are available. Does not install
# anything: prints actionable hints and fails if any required tool is missing.

source "$(dirname "$0")/lib/common.sh"

missing=0

check() {
    local name="$1"
    local apt_hint="$2"
    local brew_hint="$3"
    if command_exists "$name"; then
        log "found: $name"
    else
        printf 'missing: %s\n  apt:  %s\n  brew: %s\n' "$name" "$apt_hint" "$brew_hint" >&2
        missing=$((missing + 1))
    fi
}

# Node OR Bun is acceptable; only flag when neither is present.
check_node_or_bun() {
    if command_exists node || command_exists bun; then
        if command_exists node; then log "found: node"; fi
        if command_exists bun;  then log "found: bun";  fi
    else
        printf 'missing: node or bun\n  apt:  sudo apt install -y nodejs npm\n  brew: brew install node\n  bun:  curl -fsSL https://bun.sh/install | bash\n' >&2
        missing=$((missing + 1))
    fi
}

check docker "sudo apt install -y docker.io"     "brew install --cask docker"
check_node_or_bun
check tmux   "sudo apt install -y tmux"          "brew install tmux"
check git    "sudo apt install -y git"           "brew install git"
check gh     "see https://cli.github.com"        "brew install gh"
check jq     "sudo apt install -y jq"            "brew install jq"
check yq     "sudo curl -L -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && sudo chmod +x /usr/local/bin/yq" "brew install yq"
check curl   "sudo apt install -y curl"          "brew install curl"
check unzip  "sudo apt install -y unzip"         "brew install unzip"

if [ "$missing" -gt 0 ]; then
    die "$missing required dependency(ies) missing"
fi

log "all host dependencies present"
