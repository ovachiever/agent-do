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
#
# String values are encoded via python3's json module when available, which
# covers the full RFC 8259 string-escape requirements (all of U+0000..U+001F,
# plus \\ and \"). When python3 is unavailable, a manual fallback escapes the
# named C0 controls (\b \t \n \f \r) plus \\ and \"; other control bytes
# may pass through unescaped on that path. Values containing literal NUL bytes
# are unsupported in either path; bash strips NUL during command substitution.
#
# Environment variables:
#   AGENT_DO_SNAPSHOT_COMPACT=1   Emit single-line JSON instead of pretty-printed.
#                                 Useful for piping to jq, log lines, or other tools
#                                 that prefer one document per line.

# Accumulate snapshot fields. Two parallel arrays:
#   _SNAPSHOT_FIELDS holds entries of the form "TAG:KEY" where TAG is STRING or RAW.
#   _SNAPSHOT_VALUES holds the raw user-supplied value at the same index.
# String entries get JSON-encoded at snapshot_end; raw entries are inserted verbatim
# (used for numbers, booleans, nested JSON objects, and arrays).
_SNAPSHOT_TOOL=""
_SNAPSHOT_FIELDS=()
_SNAPSHOT_VALUES=()

snapshot_begin() {
    _SNAPSHOT_TOOL="${1:-unknown}"
    _SNAPSHOT_FIELDS=()
    _SNAPSHOT_VALUES=()
    _SNAPSHOT_FIELDS+=("STRING:tool")
    _SNAPSHOT_VALUES+=("$_SNAPSHOT_TOOL")
    _SNAPSHOT_FIELDS+=("STRING:timestamp")
    _SNAPSHOT_VALUES+=("$(date -u +%Y-%m-%dT%H:%M:%SZ)")
}

snapshot_field() {
    _SNAPSHOT_FIELDS+=("STRING:$1")
    _SNAPSHOT_VALUES+=("$2")
}

snapshot_num_field() {
    _SNAPSHOT_FIELDS+=("RAW:$1")
    _SNAPSHOT_VALUES+=("$2")
}

snapshot_bool_field() {
    _SNAPSHOT_FIELDS+=("RAW:$1")
    _SNAPSHOT_VALUES+=("$2")
}

snapshot_json_field() {
    _SNAPSHOT_FIELDS+=("RAW:$1")
    _SNAPSHOT_VALUES+=("$2")
}

snapshot_array_field() {
    _SNAPSHOT_FIELDS+=("RAW:$1")
    _SNAPSHOT_VALUES+=("$2")
}

# Manual fallback escape used when python3 is unavailable. This covers the
# named C0 controls plus backslash and double-quote, but does NOT cover the
# rest of U+0000..U+001F. Tools running in environments without python3
# should not rely on this path for arbitrary control-byte input.
_snapshot_fallback_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    value="${value//$'\b'/\\b}"
    value="${value//$'\f'/\\f}"
    printf '"%s"' "$value"
}

snapshot_end() {
    local i
    local count=${#_SNAPSHOT_FIELDS[@]}
    local -a encoded_values=()

    if command -v python3 &>/dev/null && [[ $count -gt 0 ]]; then
        # NUL-delimited values to python; one encoded JSON string per line back.
        # python3 reads stdin as bytes, splits on NUL, encodes each part with
        # json.dumps (which produces the full quoted form, e.g. "hello"), and
        # prints them one per line. Bash reads back into encoded_values.
        local encoded_output
        encoded_output=$(printf '%s\0' "${_SNAPSHOT_VALUES[@]}" | python3 -c '
import sys, json
data = sys.stdin.buffer.read()
if data.endswith(b"\x00"):
    data = data[:-1]
for p in data.split(b"\x00"):
    print(json.dumps(p.decode("utf-8")))
' 2>/dev/null) || encoded_output=""

        if [[ -n "$encoded_output" ]]; then
            local IFS=$'\n'
            read -d '' -r -a encoded_values <<< "$encoded_output" || true
        fi
    fi

    # Build the output object. Walk the parallel arrays.
    local output="{"
    local first=true
    for ((i=0; i<count; i++)); do
        local entry="${_SNAPSHOT_FIELDS[$i]}"
        local tag="${entry%%:*}"
        local key="${entry#*:}"
        local raw_value="${_SNAPSHOT_VALUES[$i]}"
        local field_json

        if [[ "$tag" == "RAW" ]]; then
            field_json="\"$key\": $raw_value"
        else
            local encoded
            if [[ ${#encoded_values[@]} -eq $count ]]; then
                encoded="${encoded_values[$i]}"
            else
                encoded=$(_snapshot_fallback_escape "$raw_value")
            fi
            field_json="\"$key\": $encoded"
        fi

        if [[ "$first" == "true" ]]; then
            first=false
        else
            output+=", "
        fi
        output+="$field_json"
    done
    output+="}"

    # Pretty-print if python3 is available, unless AGENT_DO_SNAPSHOT_COMPACT=1.
    if [[ "${AGENT_DO_SNAPSHOT_COMPACT:-}" == "1" ]]; then
        echo "$output"
    elif command -v python3 &>/dev/null; then
        echo "$output" | python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.read()), indent=2))" 2>/dev/null || echo "$output"
    else
        echo "$output"
    fi

    _SNAPSHOT_FIELDS=()
    _SNAPSHOT_VALUES=()
}

# Quick JSON error response. Composes the standard helpers so the error
# message is encoded by the same path as any other string value.
snapshot_error() {
    local message="$1"
    local tool="${2:-$_SNAPSHOT_TOOL}"
    snapshot_begin "$tool"
    snapshot_field "error" "$message"
    snapshot_end
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
