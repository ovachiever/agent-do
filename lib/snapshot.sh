#!/usr/bin/env bash
# lib/snapshot.sh — Shared snapshot formatting for agent-do tools
# Source this file to get consistent JSON output helpers.
#
# Usage in tools:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "${SCRIPT_DIR}/../lib/snapshot.sh" 2>/dev/null || true
#
#   # Then use:
#   snapshot_begin "tool-name"
#   snapshot_field "key" "value"
#   snapshot_json_field "key" '{"nested": "json"}'
#   snapshot_array_field "key" '["item1", "item2"]'
#   snapshot_end

# Accumulate snapshot fields
_SNAPSHOT_TOOL=""
_SNAPSHOT_FIELDS=()

snapshot_begin() {
    _SNAPSHOT_TOOL="${1:-unknown}"
    _SNAPSHOT_FIELDS=()
    _SNAPSHOT_FIELDS+=("\"tool\": \"$_SNAPSHOT_TOOL\"")
    _SNAPSHOT_FIELDS+=("\"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"")
}

snapshot_field() {
    local key="$1"
    local value="$2"
    # Escape quotes in value
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    _SNAPSHOT_FIELDS+=("\"$key\": \"$value\"")
}

snapshot_num_field() {
    local key="$1"
    local value="$2"
    _SNAPSHOT_FIELDS+=("\"$key\": $value")
}

snapshot_bool_field() {
    local key="$1"
    local value="$2"
    _SNAPSHOT_FIELDS+=("\"$key\": $value")
}

snapshot_json_field() {
    local key="$1"
    local json="$2"
    _SNAPSHOT_FIELDS+=("\"$key\": $json")
}

snapshot_array_field() {
    local key="$1"
    local json="$2"
    _SNAPSHOT_FIELDS+=("\"$key\": $json")
}

snapshot_end() {
    local output="{"
    local first=true
    for field in "${_SNAPSHOT_FIELDS[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            output+=", "
        fi
        output+="$field"
    done
    output+="}"
    # Pretty-print if python3 available
    if command -v python3 &>/dev/null; then
        echo "$output" | python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.read()), indent=2))" 2>/dev/null || echo "$output"
    else
        echo "$output"
    fi
    _SNAPSHOT_FIELDS=()
}

# Quick JSON error response
snapshot_error() {
    local message="$1"
    local tool="${2:-$_SNAPSHOT_TOOL}"
    echo "{\"tool\": \"$tool\", \"error\": \"$message\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
}

# Check if a command exists and report
snapshot_check_tool() {
    local name="$1"
    local cmd="${2:-$1}"
    if command -v "$cmd" &>/dev/null; then
        echo "true"
    else
        echo "false"
    fi
}
