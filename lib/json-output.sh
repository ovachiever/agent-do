#!/usr/bin/env bash
# lib/json-output.sh — Shared JSON output helpers for agent-do tools
# Source this file to get --json flag support and structured output.
#
# Usage in tools:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "${SCRIPT_DIR}/../lib/json-output.sh" 2>/dev/null || true
#
#   # Parse --json flag from args:
#   parse_output_format "$@"  # Sets OUTPUT_FORMAT=json|text
#
#   # Wrap output:
#   json_success "result text or data"
#   json_error "error message"
#   json_result '{"key": "value"}'  # Pass raw JSON
#
#   # Or use conditional output:
#   if [[ "$OUTPUT_FORMAT" == "json" ]]; then
#       json_success "$data"
#   else
#       echo "$data"
#   fi

OUTPUT_FORMAT="${OUTPUT_FORMAT:-text}"

# Parse --json from argument list, return remaining args
parse_output_format() {
    local args=()
    for arg in "$@"; do
        if [[ "$arg" == "--json" ]]; then
            OUTPUT_FORMAT="json"
        else
            args+=("$arg")
        fi
    done
    # Store cleaned args for caller to use
    PARSED_ARGS=("${args[@]}")
}

# Success response wrapping text output
json_success() {
    local data="$1"
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        python3 -c "
import json, sys
data = sys.argv[1]
# Try to parse as JSON first
try:
    parsed = json.loads(data)
    print(json.dumps({'success': True, 'result': parsed}, indent=2))
except:
    print(json.dumps({'success': True, 'result': data}, indent=2))
" "$data"
    else
        echo "$data"
    fi
}

# Error response
json_error() {
    local message="$1"
    local code="${2:-1}"
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        python3 -c "
import json, sys
print(json.dumps({'success': False, 'error': sys.argv[1], 'code': int(sys.argv[2])}, indent=2))
" "$message" "$code"
    else
        echo "Error: $message" >&2
    fi
    return "$code"
}

# Pass-through raw JSON result
json_result() {
    local json_data="$1"
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    print(json.dumps({'success': True, 'result': data}, indent=2))
except:
    print(json.dumps({'success': True, 'result': sys.argv[1]}, indent=2))
" "$json_data"
    else
        # Pretty-print JSON for human reading
        echo "$json_data" | python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.read()), indent=2))" 2>/dev/null || echo "$json_data"
    fi
}

# List output (one item per line in text mode, JSON array in json mode)
json_list() {
    local items="$1"  # Newline-separated items
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        python3 -c "
import json, sys
items = [line.strip() for line in sys.argv[1].split('\n') if line.strip()]
print(json.dumps({'success': True, 'count': len(items), 'items': items}, indent=2))
" "$items"
    else
        echo "$items"
    fi
}
