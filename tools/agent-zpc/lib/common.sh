#!/usr/bin/env bash
# lib/common.sh — Shared ZPC utilities
# Sourced by agent-zpc main entry. Do not run directly.

ZPC_GLOBAL_DIR="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc"

# Walk up from cwd to find .zpc/ directory
resolve_zpc_dir() {
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        [[ -d "$dir/.zpc" ]] && echo "$dir/.zpc" && return 0
        dir="$(dirname "$dir")"
    done
    return 1
}

# Directory variables — set by init_zpc_dirs
ZPC_DIR=""
ZPC_MEMORY_DIR=""
ZPC_STATE_DIR=""
ZPC_TEAM_DIR=""

init_zpc_dirs() {
    ZPC_DIR="$(resolve_zpc_dir)" || return 1
    ZPC_MEMORY_DIR="$ZPC_DIR/memory"
    ZPC_STATE_DIR="$ZPC_DIR/.state"
    ZPC_TEAM_DIR="$ZPC_DIR/team"
}

ensure_zpc() {
    init_zpc_dirs || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "No .zpc/ directory found. Run 'agent-do zpc init' first." 1
        else
            echo "Error: No .zpc/ directory found. Run 'agent-do zpc init' first." >&2
        fi
        exit 1
    }
}

ensure_global() {
    mkdir -p "$ZPC_GLOBAL_DIR"
}

today() { date +%Y-%m-%d; }

count_lines() {
    local file="$1"
    [[ -f "$file" && -s "$file" ]] && wc -l < "$file" | tr -d ' ' || echo "0"
}

validate_json() {
    echo "$1" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null
}

append_jsonl() {
    local file="$1" line="$2"
    validate_json "$line" || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Invalid JSON: $line" 1
        else
            echo "Error: Invalid JSON" >&2
        fi
        return 1
    }
    echo "$line" >> "$file"
}

read_jsonl() {
    local file="$1" count="${2:-20}"
    [[ -f "$file" && -s "$file" ]] && tail -n "$count" "$file" || true
}

die() {
    local msg="$1"
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_error "$msg" 1
    else
        echo "Error: $msg" >&2
    fi
    exit 1
}
