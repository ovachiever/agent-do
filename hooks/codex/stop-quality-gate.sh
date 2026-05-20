#!/bin/bash
# Stop hook: advisory DPT quality report when Codex finishes a turn.
#
# Runs stop-quality-gate.py which scores the current agent-do browse session
# via agent-do dpt and surfaces the result as additionalContext for the model.
# This hook does not block; missing verification is surfaced as context only.
#
# Auto-commit is not chained here. agent-do does not ship git automation.
# If you want auto-commit at Stop, register your own auto-commit script under
# a separate Stop hook entry in ~/.codex/hooks.json.

set -euo pipefail

INPUT=$(cat)
RESULT=$(printf '%s' "$INPUT" | python3 ~/.codex/hooks/stop-quality-gate.py)

printf '%s\n' "$RESULT"

exit 0
