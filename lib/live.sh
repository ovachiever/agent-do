#!/usr/bin/env bash
# Shared shell integration for the +live runtime modifier.

set -euo pipefail

live_is_modifier() {
    local token="${1:-}"
    [[ "$token" == "+live" || "$token" == +live\(*\) ]]
}

live_export_context() {
    local modifier="${1:-}"
    local script_dir="${2:-}"
    [[ -n "$modifier" ]] || return 0

    local live_json
    if ! live_json="$(python3 - "$modifier" "$script_dir" <<'PY'
import json
import sys
from pathlib import Path

modifier = sys.argv[1]
script_dir = Path(sys.argv[2])
sys.path.insert(0, str(script_dir / "lib"))

from live.parser import parse_live_modifier  # noqa: E402

print(json.dumps(parse_live_modifier(modifier)))
PY
    )"; then
        echo "Invalid runtime modifier: $modifier" >&2
        exit 1
    fi

    export AGENT_DO_LIVE=1
    export AGENT_DO_LIVE_SPEC="$modifier"
    export AGENT_DO_LIVE_CONTEXT="$live_json"
}
