#!/usr/bin/env bash
# Test script for agent-do

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DO="$SCRIPT_DIR/agent-do"
TEST_HOME="$(mktemp -d)"
PASS=0
FAIL=0

cleanup() {
    rm -rf "$TEST_HOME"
}
trap cleanup EXIT

export AGENT_DO_HOME="$TEST_HOME"

pass() {
    echo "  ✓ $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "  ✗ $1"
    echo "    $2"
    FAIL=$((FAIL + 1))
}

check_cmd() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc" "command failed: $*"
    fi
}

check_output() {
    local desc="$1"
    local pattern="$2"
    shift 2
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | grep -q "$pattern"; then
        pass "$desc"
    else
        fail "$desc" "expected pattern '$pattern', got: $(echo "$output" | head -3)"
    fi
}

echo "Testing agent-do..."
echo

check_cmd "--help works" "$AGENT_DO" --help
check_cmd "--list works" "$AGENT_DO" --list
check_cmd "creds help works" "$AGENT_DO" creds --help
check_cmd "notify help works" "$AGENT_DO" notify --help
check_cmd "nudges stats works" "$AGENT_DO" nudges stats
check_cmd "bootstrap --help works" "$AGENT_DO" bootstrap --help
check_output "--status works in isolated home" "No active sessions." "$AGENT_DO" --status
check_output "--health works" "Summary:" "$AGENT_DO" --health
check_output "--raw executes a directory-backed tool" "agent-context" "$AGENT_DO" --raw context --help
check_output "--offline routes iOS screenshot intent" "agent-ios screenshot" "$AGENT_DO" --offline "screenshot the iOS simulator"
check_output "--offline routes network scan intent" "agent-network scan --port 3000" "$AGENT_DO" --offline "what's using port 3000"
check_output "pattern matcher JSON uses iOS tool" '"tool": "ios"' "$SCRIPT_DIR/bin/pattern-matcher" --json "screenshot the iOS simulator"
check_cmd "v1.1 routing foundation tests" python3 "$SCRIPT_DIR/tests/test_v11_routing.py"
check_cmd "credential tests" python3 "$SCRIPT_DIR/tests/test_creds.py"
check_cmd "dispatch tests" python3 "$SCRIPT_DIR/tests/test_dispatch.py"
check_cmd "auth tests" python3 "$SCRIPT_DIR/tests/test_auth.py"
check_cmd "auth interactive tests" python3 "$SCRIPT_DIR/tests/test_auth_interactive.py"
check_cmd "auth live-browser tests" python3 "$SCRIPT_DIR/tests/test_auth_live_browser.py"
check_cmd "auth adapter tests" python3 "$SCRIPT_DIR/tests/test_auth_adapters.py"
check_cmd "auth provider refresh tests" python3 "$SCRIPT_DIR/tests/test_auth_provider_refresh.py"
check_cmd "auth email challenge tests" python3 "$SCRIPT_DIR/tests/test_auth_email_challenge.py"
check_cmd "auth phone challenge tests" python3 "$SCRIPT_DIR/tests/test_auth_phone_challenge.py"
check_cmd "auth passkey tests" python3 "$SCRIPT_DIR/tests/test_auth_passkey.py"
check_cmd "auth probe tests" python3 "$SCRIPT_DIR/tests/test_auth_probe.py"
check_cmd "auth advance tests" python3 "$SCRIPT_DIR/tests/test_auth_advance.py"
check_cmd "email tests" python3 "$SCRIPT_DIR/tests/test_email.py"
check_cmd "sms tests" python3 "$SCRIPT_DIR/tests/test_sms.py"
check_cmd "live runtime tests" python3 "$SCRIPT_DIR/tests/test_live.py"
check_cmd "spec tests" python3 "$SCRIPT_DIR/tests/test_spec.py"
check_cmd "resend tests" python3 "$SCRIPT_DIR/tests/test_resend.py"
check_cmd "render tests" python3 "$SCRIPT_DIR/tests/test_render.py"
check_cmd "gh tests" python3 "$SCRIPT_DIR/tests/test_gh.py"
check_cmd "hardware tests" python3 "$SCRIPT_DIR/tests/test_hardware.py"
check_cmd "meetings tests" python3 "$SCRIPT_DIR/tests/test_meetings.py"
check_cmd "notify tests" python3 "$SCRIPT_DIR/tests/test_notify.py"
check_cmd "coord tests" python3 "$SCRIPT_DIR/tests/test_coord.py"
check_cmd "browser import tests" python3 "$SCRIPT_DIR/tests/test_browser_import.py"
check_cmd "browse session default tests" python3 "$SCRIPT_DIR/tests/test_browse_session_defaults.py"
check_cmd "tool regression tests" python3 "$SCRIPT_DIR/tests/test_tool_regressions.py"

# lib/snapshot.sh: AGENT_DO_SNAPSHOT_COMPACT=1 produces single-line JSON.
snapshot_compact_output=$(
    AGENT_DO_SNAPSHOT_COMPACT=1 bash -c "
        source '$SCRIPT_DIR/lib/snapshot.sh'
        snapshot_begin 'compact-test'
        snapshot_field 'key' 'value'
        snapshot_end
    " 2>&1
)
if [[ "$snapshot_compact_output" != *$'\n'* ]] && \
   printf '%s' "$snapshot_compact_output" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' 2>/dev/null; then
    pass "snapshot compact mode emits single-line JSON"
else
    fail "snapshot compact mode emits single-line JSON" "output: $snapshot_compact_output"
fi

# lib/snapshot.sh: snapshot_field encodes the full RFC 8259 control range
# (all of U+0000..U+001F plus backslash and double-quote) when python3 is
# available. Exercises named controls plus arbitrary control bytes (SOH, ESC,
# DEL) that the previous manual-escape implementation passed through raw.
snapshot_encode_output=$(
    bash -c '
        source "$0/lib/snapshot.sh"
        snapshot_begin encode-test
        snapshot_field tab        "$(printf "a\tb")"
        snapshot_field cr         "$(printf "a\rb")"
        snapshot_field bs         "$(printf "a\bb")"
        snapshot_field ff         "$(printf "a\fb")"
        snapshot_field lf         "$(printf "a\nb")"
        snapshot_field soh        "$(printf "a\x01b")"
        snapshot_field esc        "$(printf "a\x1bb")"
        snapshot_field del        "$(printf "a\x7fb")"
        snapshot_field unicode    "Unicode: 日本語 🌟"
        snapshot_field backslash  "C:\\Users\\ct"
        snapshot_field quote      "she said \"hi\""
        snapshot_field empty      ""
        snapshot_end
    ' "$SCRIPT_DIR" 2>&1
)
if echo "$snapshot_encode_output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
# Round-trip values that include named C0 controls, arbitrary controls,
# unicode, backslash, quote, and empty string.
assert d["tab"] == "a\tb"
assert d["soh"] == "a\x01b"
assert d["esc"] == "a\x1bb"
assert d["unicode"] == "Unicode: 日本語 🌟"
assert d["empty"] == ""
' 2>/dev/null; then
    pass "snapshot_field encodes full RFC 8259 control range"
else
    fail "snapshot_field encodes full RFC 8259 control range" "invalid or wrong JSON: $snapshot_encode_output"
fi

# lib/snapshot.sh: snapshot_error encodes its message via the same path,
# so messages containing quotes, controls, or backslashes round-trip cleanly.
snapshot_error_output=$(
    bash -c '
        source "$0/lib/snapshot.sh"
        snapshot_begin err-test
        snapshot_error "boom: \"quoted\" with$(printf "\ttab")$(printf "\nlf")"
    ' "$SCRIPT_DIR" 2>&1
)
if echo "$snapshot_error_output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
assert d["error"] == "boom: \"quoted\" with\ttab\nlf"
' 2>/dev/null; then
    pass "snapshot_error encodes message via JSON encoder"
else
    fail "snapshot_error encodes message via JSON encoder" "invalid or wrong JSON: $snapshot_error_output"
fi

# lib/snapshot.sh: invalid UTF-8 in one field must not poison sibling fields.
# Pre-fix behavior: a single bad-UTF-8 value caused python encoding to abort,
# the whole snapshot fell back to manual escaping, and unrelated control bytes
# in other fields silently lost their \u-escaping (and the snapshot's overall
# bytes were no longer valid UTF-8). Post-fix: the bad value is encoded via
# errors="replace" (U+FFFD substitution) and other fields keep full encoder.
snapshot_bounded_output=$(
    bash -c '
        source "$0/lib/snapshot.sh"
        snapshot_begin bounded-test
        snapshot_field ascii   "hello"
        snapshot_field ctrl    "$(printf "a\x01b")"
        snapshot_field bad     "$(printf "before\xc3\x28after")"
        snapshot_field other   "$(printf "x\x02y")"
        AGENT_DO_SNAPSHOT_COMPACT=1 snapshot_end
    ' "$SCRIPT_DIR" 2>&1
)
if printf '%s' "$snapshot_bounded_output" | python3 -c '
import sys, json
data = sys.stdin.buffer.read()
# Snapshot output must be valid UTF-8 even when a value contains invalid bytes.
text = data.decode("utf-8")
d = json.loads(text)
# Clean fields must keep full encoder semantics (control chars escaped).
assert d["ctrl"] == "a\x01b"
assert d["other"] == "x\x02y"
# Bad-bytes field gets U+FFFD substitution; we just verify it round-trips and
# the surrounding text is intact.
assert d["bad"].startswith("before")
assert d["bad"].endswith("(after")
' 2>/dev/null; then
    pass "snapshot bad-UTF-8 field does not poison siblings"
else
    fail "snapshot bad-UTF-8 field does not poison siblings" "invalid or wrong JSON: $snapshot_bounded_output"
fi

BOOTSTRAP_PROJECT="$TEST_HOME/bootstrap-project"
mkdir -p "$BOOTSTRAP_PROJECT"
cat > "$BOOTSTRAP_PROJECT/CLAUDE.md" <<'EOF'
## agent-do Tooling

Use `agent-do context`
Use `agent-do zpc`
EOF

check_output "bootstrap recommendation detects pending work" '"needs_bootstrap": true' "$AGENT_DO" bootstrap --recommend --json --cwd "$BOOTSTRAP_PROJECT"
check_output "bootstrap initializes context and zpc" "Initialized: context, zpc" "$AGENT_DO" bootstrap --cwd "$BOOTSTRAP_PROJECT"
check_cmd "bootstrap created project-local .zpc" test -d "$BOOTSTRAP_PROJECT/.zpc"

echo
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1
