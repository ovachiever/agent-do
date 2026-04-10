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

# Find browser daemon
TMPDIR_ACTUAL="$(python3 -c 'import tempfile; print(tempfile.gettempdir())' 2>/dev/null)"
SOCK=$(find "$TMPDIR_ACTUAL" -name 'agent-browser-*.sock' -type s 2>/dev/null | head -1)

# === MODE 2: No browse session — WARN LOUDLY ===
if [[ -z "$SOCK" || ! -S "$SOCK" ]]; then
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
# Resolve engine path: check common locations
DPT_ENGINE=""
for candidate in \
    "$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")")/dist/dpt-engine.js" \
    "$HOME/Documents/AI/Custom_Coding/dpt/dist/dpt-engine.js" \
    "$(dirname "$SOCK" 2>/dev/null)/../dpt/dist/dpt-engine.js"; do
    if [[ -f "$candidate" ]]; then
        DPT_ENGINE="$candidate"
        break
    fi
done
if [[ -z "$DPT_ENGINE" || ! -f "$DPT_ENGINE" ]]; then
    python3 -c "
import json
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': 'DPT engine not found. Run: agent-do dpt build'}}
print(json.dumps(output))
"
    exit 0
fi

SCORE_OUTPUT=$(python3 -c "
import json, socket, sys, os

engine_path = sys.argv[1]
sock_path = sys.argv[2]

with open(engine_path, 'r') as f:
    js = f.read()

msg = json.dumps({'id': 'dpt-hook', 'action': 'evaluate', 'script': js})
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(sock_path)
    s.sendall(msg.encode('utf-8') + b'\n')
    chunks = []
    while True:
        try:
            chunk = s.recv(131072)
            if not chunk: break
            chunks.append(chunk)
            try:
                json.loads(b''.join(chunks)); break
            except json.JSONDecodeError: continue
        except socket.timeout: break
    s.close()
    raw = b''.join(chunks).decode('utf-8', errors='replace')
    resp = json.loads(raw)
    if resp.get('success'):
        result = resp.get('data', {}).get('result', {})
        if isinstance(result, str): result = json.loads(result)
        syn = result.get('synthesis', {})
        dims = syn.get('dimensions', {})
        meta = result.get('meta', {})
        score = syn.get('overall_score', '?')
        grade = syn.get('overall_grade', '?')

        # Include scored URL so agent can judge relevance to the edited file
        url = meta.get('url', '')
        from urllib.parse import urlparse
        path = urlparse(url).path if url else '?'

        dp = [f'{k[:3]}{dims.get(k,{}).get(\"score\",\"?\")}' for k in ['chromatic','typography','spatial','attention','coherence']]
        line = f'DPT: {score} {grade} ({\" \".join(dp)}) scored:{path}'

        # Only show delta if baseline exists — no findings, no imperatives
        baseline_path = '/tmp/dpt-baseline.json'
        if os.path.exists(baseline_path):
            with open(baseline_path) as bf:
                bl = json.load(bf)
            bl_score = bl.get('synthesis', {}).get('overall_score', 0)
            delta = score - bl_score if isinstance(score, int) else 0
            if delta != 0:
                arrow = '+' if delta > 0 else ''
                line += f' ({arrow}{delta} vs baseline)'

        print(line)
except Exception as e:
    print(f'DPT hook error: {e}')
" "$DPT_ENGINE" "$SOCK" 2>/dev/null) || true

if [[ -n "$SCORE_OUTPUT" ]]; then
    python3 -c "
import json, sys
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': sys.argv[1]}}
print(json.dumps(output))
" "$SCORE_OUTPUT"
fi
