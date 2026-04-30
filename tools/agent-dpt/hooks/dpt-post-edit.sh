#!/usr/bin/env bash
# DPT PostToolUse hook — design quality feedback after CSS/HTML/JSX edits
# Two modes:
#   1. Browse session active → wait for HMR → inject engine → return score
#   2. No browse session → WARN that design files are being edited blind

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except: print('')
" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0

# Check if file is design-related
IS_DESIGN=false
case "$FILE_PATH" in
    *.css|*.scss|*.less|*.html|*.jsx|*.tsx|*.vue|*.svelte) IS_DESIGN=true ;;
    *tailwind.config*|*theme*|*styles*|*global*) IS_DESIGN=true ;;
esac

[[ "$IS_DESIGN" == false ]] && exit 0

# Check the current agent-scoped browse session. Do not grab the first socket on
# disk; that can belong to another agent or a stale daemon.
BROWSE_STATUS="$(agent-do browse status --json 2>/dev/null || true)"
BROWSE_READY="$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    print('1' if data.get('daemon', {}).get('running') and data.get('browser', {}).get('responsive') else '0')
except Exception:
    print('0')
" "$BROWSE_STATUS")"

# === MODE 2: No browse session — WARN LOUDLY ===
if [[ "$BROWSE_READY" != "1" ]]; then
    python3 -c "
import json
msg = 'WARNING: You are editing design files WITHOUT a browser session. '
msg += 'DPT cannot score your changes. You are flying blind. '
msg += 'REQUIRED: Run \`agent-do browse open <dev-url>\` NOW, then \`agent-do dpt baseline\` before making more changes. '
msg += 'Do NOT continue editing design files without visual verification.'
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}}
print(json.dumps(output))
"
    exit 0
fi

# === Wait for HMR to update the browser ===
# The edit just completed. The dev server needs time to recompile and push
# the update via HMR websocket. Without this wait, DPT scores the stale
# pre-edit page — the #1 source of false positives (e.g. "no primary CTA"
# when the edit just added one).
sleep 2

# === MODE 1: Browse session active — score and report ===
SCORE_OUTPUT="$(agent-do dpt score --current --quiet 2>/dev/null || true)"

if [[ -n "$SCORE_OUTPUT" ]]; then
    python3 -c "
import json, sys
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': sys.argv[1]}}
print(json.dumps(output))
" "$SCORE_OUTPUT"
fi
