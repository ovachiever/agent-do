#!/usr/bin/env bash
# Test script for agent-do

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/bash-runtime.sh
source "$SCRIPT_DIR/lib/bash-runtime.sh"
agent_do_ensure_supported_bash "$SCRIPT_DIR/test.sh" "$@" || exit $?

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
    local output
    if output=$("$@" 2>&1); then
        pass "$desc"
    else
        fail "$desc" "command failed: $*"
        echo "$output" | tail -15 | sed 's/^/      | /'
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

check_error_output() {
    local desc="$1"
    local pattern="$2"
    shift 2
    local output rc
    output=$("$@" 2>&1); rc=$?
    if [[ $rc -eq 1 ]] && echo "$output" | grep -q "$pattern"; then
        pass "$desc"
    else
        fail "$desc" "expected exit 1 and pattern '$pattern', rc=$rc, got: $(echo "$output" | head -3)"
    fi
}

find_macos_test_python() {
    # Dependency tests use the active Python environment. The macOS integration
    # test must instead use an interpreter that owns the platform frameworks.
    local candidate=""
    for candidate in \
        "${AGENT_DO_MACOS_TEST_PYTHON:-}" \
        "$(command -v python3 2>/dev/null || true)" \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        /usr/bin/python3
    do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        if "$candidate" -c 'import AppKit, Foundation' >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
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
check_cmd "transcribe tests" python3 "$SCRIPT_DIR/tests/test_transcribe.py"
check_cmd "handbrake tests" python3 "$SCRIPT_DIR/tests/test_handbrake.py"
check_cmd "substack tests" python3 "$SCRIPT_DIR/tests/test_substack.py"
check_cmd "suggest AI routing tests" python3 "$SCRIPT_DIR/tests/test_suggest_ai.py"
check_cmd "prompt hook AI routing tests" python3 "$SCRIPT_DIR/tests/test_prompt_hook_ai.py"
check_cmd "model resolution tests" python3 "$SCRIPT_DIR/tests/test_models.py"
check_cmd "manna serve tests" python3 "$SCRIPT_DIR/tests/test_manna_serve.py"
check_cmd "install spec coherence" python3 "$SCRIPT_DIR/tests/test_install_specs.py"
check_cmd "generated discovery index tests" bash "$SCRIPT_DIR/tests/test_index_generation.sh"
check_cmd "zpc global read-surface tests" python3 "$SCRIPT_DIR/tests/test_zpc_global.py"
check_cmd "zpc position ledger tests" python3 "$SCRIPT_DIR/tests/test_zpc_position.py"
check_cmd "zpc auto-counsel tests" python3 "$SCRIPT_DIR/tests/test_zpc_counsel_auto.py"
check_cmd "zpc epistemics tests" python3 "$SCRIPT_DIR/tests/test_zpc_epistemics.py"
check_cmd "brief estate engine tests" python3 "$SCRIPT_DIR/tests/test_brief.py"
check_cmd "zpc delivery tests" python3 "$SCRIPT_DIR/tests/test_zpc_delivery.py"
check_cmd "zpc memory bounds tests" python3 "$SCRIPT_DIR/tests/test_zpc_memory_bounds.py"
check_cmd "zpc re-litigation tests" python3 "$SCRIPT_DIR/tests/test_zpc_relitigate.py"
check_cmd "zpc preference slice tests" python3 "$SCRIPT_DIR/tests/test_zpc_preferences.py"
check_cmd "zpc trigger gate and delivery tests" python3 "$SCRIPT_DIR/tests/test_zpc_triggers.py"
check_cmd "zpc store-only init tests" python3 "$SCRIPT_DIR/tests/test_zpc_init_store_only.py"
check_cmd "zpc store walk bounds tests" python3 "$SCRIPT_DIR/tests/test_zpc_store_walk.py"
check_cmd "hook store resolution tests" python3 "$SCRIPT_DIR/tests/test_hook_store_resolution.py"
check_cmd "session-start read tests" python3 "$SCRIPT_DIR/tests/test_session_start_reads.py"
check_cmd "now stamp hook tests" python3 "$SCRIPT_DIR/tests/test_now_stamp.py"
check_cmd "quantity write-check hook tests" python3 "$SCRIPT_DIR/tests/test_quantity_write_check.py"
check_cmd "record age rendering tests" python3 "$SCRIPT_DIR/tests/test_record_ages.py"
check_cmd "context retrieve authority tests" python3 "$SCRIPT_DIR/tests/test_context_retrieve_authority.py"
check_cmd "api template tests" python3 "$SCRIPT_DIR/tests/test_api_templates.py"
check_cmd "supabase management tests" python3 "$SCRIPT_DIR/tests/test_supabase_management.py"
check_cmd "credential tests" python3 "$SCRIPT_DIR/tests/test_creds.py"
check_cmd "notion tests" python3 "$SCRIPT_DIR/tests/test_notion.py"
check_cmd "bash runtime tests" python3 "$SCRIPT_DIR/tests/test_bash_runtime.py"
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
macos_test_python="$(find_macos_test_python || true)"
if [[ -n "$macos_test_python" ]]; then
    macos_test_bin="$(dirname "$macos_test_python")"
    check_cmd "live runtime tests" env PATH="$macos_test_bin:$PATH" "$macos_test_python" "$SCRIPT_DIR/tests/test_live.py"
else
    check_cmd "live runtime tests" python3 "$SCRIPT_DIR/tests/test_live.py"
fi
check_cmd "appleevents tests" python3 "$SCRIPT_DIR/tests/test_appleevents.py"
check_cmd "spec tests" python3 "$SCRIPT_DIR/tests/test_spec.py"
check_cmd "resend tests" python3 "$SCRIPT_DIR/tests/test_resend.py"
check_cmd "render tests" python3 "$SCRIPT_DIR/tests/test_render.py"
check_cmd "psql tests" python3 "$SCRIPT_DIR/tests/test_psql.py"
check_cmd "vector tests" python3 "$SCRIPT_DIR/tests/test_vector.py"
check_output "vector --help" "today" "$AGENT_DO" vector --help
check_cmd "gh tests" python3 "$SCRIPT_DIR/tests/test_gh.py"
check_cmd "coderabbit tests" python3 "$SCRIPT_DIR/tests/test_coderabbit.py"
check_cmd "ci triage tests" python3 "$SCRIPT_DIR/tests/test_ci_triage.py"
check_cmd "git guardrail tests" python3 "$SCRIPT_DIR/tests/test_git_guardrails.py"
check_cmd "worktree binding tests" python3 "$SCRIPT_DIR/tests/test_worktree_binding.py"
check_cmd "hardware tests" python3 "$SCRIPT_DIR/tests/test_hardware.py"
check_cmd "meetings tests" python3 "$SCRIPT_DIR/tests/test_meetings.py"
check_cmd "harness tests" python3 "$SCRIPT_DIR/tests/test_harness.py"
check_cmd "quantity authority tests" python3 "$SCRIPT_DIR/tests/test_quantities.py"
# Contract drift executes each registered tool's real help surface. Build the
# release binary selected by the Manna wrapper first so the result cannot
# depend on a stale or missing per-worktree artifact.
check_cmd "manna release binary is current" cargo build --quiet --release --manifest-path "$SCRIPT_DIR/tools/agent-manna/Cargo.toml"
check_cmd "manna estate tests" python3 "$SCRIPT_DIR/tests/test_manna_estate.py"
check_cmd "contracts gate tests" python3 "$SCRIPT_DIR/tests/test_contracts_gate.py"
check_cmd "contracts drift tests" python3 "$SCRIPT_DIR/tests/test_contracts_drift.py"
check_cmd "contracts audit tests" python3 "$SCRIPT_DIR/tests/test_contracts_audit.py"
check_cmd "bounds gate tests" python3 "$SCRIPT_DIR/tests/test_bounds_gate.py"
check_cmd "routing contracts tests" python3 "$SCRIPT_DIR/tests/test_routing_contracts.py"
check_cmd "contracts drift channel empty" "$AGENT_DO" harness contracts drift
check_cmd "bounds drift clean against the authority" "$AGENT_DO" harness bounds drift
check_output "contracts validate gates bounds too" "Bounds:" "$AGENT_DO" harness contracts validate
check_cmd "tools reference doc in sync" "$SCRIPT_DIR/bin/gen-tools-doc" --check
check_cmd "health probe tests" python3 "$SCRIPT_DIR/tests/test_health_probes.py"
check_cmd "hook outcome telemetry tests" python3 "$SCRIPT_DIR/tests/test_hook_outcome_telemetry.py"
check_cmd "global hook nonblocking tests" python3 "$SCRIPT_DIR/tests/test_global_hooks_nonblocking.py"
check_cmd "nudge smarts tests" python3 "$SCRIPT_DIR/tests/test_nudge_smarts.py"
check_cmd "notify tests" python3 "$SCRIPT_DIR/tests/test_notify.py"
check_cmd "slack tests" python3 "$SCRIPT_DIR/tests/test_slack.py"
check_cmd "coord tests" python3 "$SCRIPT_DIR/tests/test_coord.py"
check_cmd "coord v2 tests" python3 "$SCRIPT_DIR/tests/test_coord_v2.py"
check_cmd "obsidian tests" python3 "$SCRIPT_DIR/tests/test_obsidian.py"
check_cmd "browser import tests" python3 "$SCRIPT_DIR/tests/test_browser_import.py"
check_cmd "browse daemon isolation tests" python3 "$SCRIPT_DIR/tests/test_browse_daemon_isolation.py"
check_cmd "browse session default tests" python3 "$SCRIPT_DIR/tests/test_browse_session_defaults.py"
check_cmd "tool regression tests" python3 "$SCRIPT_DIR/tests/test_tool_regressions.py"
check_cmd "dpt offline tests" python3 "$SCRIPT_DIR/tests/test_dpt.py"
check_cmd "dpt browser integration tests" bash "$SCRIPT_DIR/tools/agent-dpt/test/integration.sh"
check_cmd "mongo tests" python3 "$SCRIPT_DIR/tests/test_mongo.py"
check_cmd "manna unit tests" cargo test --quiet --manifest-path "$SCRIPT_DIR/tools/agent-manna/Cargo.toml"
check_cmd "manna integration tests" bash "$SCRIPT_DIR/tools/agent-manna/test/integration.sh"

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

# --- agent-sentry ---
check_output "sentry help includes PROJECTS header" "PROJECTS" "$AGENT_DO" sentry --help
check_output "sentry help lists snapshot command" "snapshot" "$AGENT_DO" sentry --help
check_error_output "sentry unknown command exits with error" "Unknown command" "$AGENT_DO" sentry bogus-command-xyz

check_output "bootstrap recommendation detects pending work" '"needs_bootstrap": true' "$AGENT_DO" bootstrap --recommend --json --cwd "$BOOTSTRAP_PROJECT"
check_output "bootstrap ask prompt names the project root" "$BOOTSTRAP_PROJECT" "$AGENT_DO" bootstrap --recommend --json --cwd "$BOOTSTRAP_PROJECT"
check_output "bootstrap --never opts the root out" "will not be asked" "$AGENT_DO" bootstrap --never --cwd "$BOOTSTRAP_PROJECT"
check_output "opted-out root reports nothing pending" '"needs_bootstrap": false' "$AGENT_DO" bootstrap --recommend --json --cwd "$BOOTSTRAP_PROJECT"
check_output "opted-out root is flagged in JSON" '"opted_out": true' "$AGENT_DO" bootstrap --recommend --json --cwd "$BOOTSTRAP_PROJECT"
check_output "bootstrap --allow restores the offer" "may be offered" "$AGENT_DO" bootstrap --allow --cwd "$BOOTSTRAP_PROJECT"
check_output "bootstrap initializes context, zpc, and workflow" "Initialized: context, zpc, manna" "$AGENT_DO" bootstrap --cwd "$BOOTSTRAP_PROJECT"
check_cmd "bootstrap created project-local .zpc" test -d "$BOOTSTRAP_PROJECT/.zpc"
check_cmd "bootstrap created project-local .manna workflow" test -f "$BOOTSTRAP_PROJECT/.manna/workflow.yaml"
check_cmd "bootstrap created federation identity" test -f "$BOOTSTRAP_PROJECT/.manna/federation.yaml"
check_cmd "bootstrap created tracked handoff root" test -f "$BOOTSTRAP_PROJECT/.handoff/README.md"

echo
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] || exit 1
