#!/usr/bin/env bash
# Integration tests for manna
# Usage: ./test/integration.sh

set -euo pipefail

# ============================================================================
# Setup
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANNA="$SCRIPT_DIR/../agent-manna"
TEST_DIR=$(mktemp -d)
PASSED=0
FAILED=0
export AGENT_DO_HOME="$TEST_DIR/.agent-do-home"

# Build the Rust binary so this test validates the current source tree.
if ! cargo build --release --quiet --manifest-path "$SCRIPT_DIR/../Cargo.toml"; then
    echo "ERROR: cargo build --release failed"
    exit 2
fi

MANNA_CORE="$SCRIPT_DIR/../target/release/manna-core"
if [[ ! -x "$MANNA_CORE" ]]; then
    echo "ERROR: expected Rust binary not found at $MANNA_CORE"
    exit 2
fi

if [[ ! -x "$MANNA" ]]; then
    echo "ERROR: manna wrapper not executable at $MANNA"
    exit 2
fi

cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

# Set unique session ID for tests
export MANNA_SESSION_ID="ses_test_$$"
export MANNA_SESSION_TOKEN="integration-test-token-0123456789abcdef0123456789abcdef"

# ============================================================================
# Test Helpers
# ============================================================================

pass() {
    echo "  ✓ $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "  ✗ $1"
    echo "    $2"
    FAILED=$((FAILED + 1))
}

# Check YAML output starts with expected prefix
check_yaml() {
    local output="$1"
    local expected="$2"
    local desc="$3"
    
    if [[ "$output" == *"$expected"* ]]; then
        pass "$desc"
    else
        fail "$desc" "Expected '$expected' in output, got: $output"
    fi
}

# Check exit code is expected
check_exit() {
    local expected="$1"
    local actual="$2"
    local desc="$3"
    
    if [[ "$actual" -eq "$expected" ]]; then
        pass "$desc"
    else
        fail "$desc" "Expected exit code $expected, got $actual"
    fi
}

# Extract ID from YAML output (id: mn-xxxxxx)
extract_id() {
    local output="$1"
    echo "$output" | grep -o 'id: mn-[a-f0-9]*' | head -1 | awk '{print $2}'
}

# Assert the complete release list, including the empty-list response contract.
check_released() {
    local output="$1"
    local desc="$2"
    shift 2
    if DONE_OUTPUT="$output" python3 - "$@" <<'PY'
import os, sys, yaml
data = yaml.safe_load(os.environ['DONE_OUTPUT'])
assert data['success'] is True
assert data['released'] == sys.argv[1:], data
PY
    then
        pass "$desc"
    else
        fail "$desc" "$output"
    fi
}

# ============================================================================
# Test Suite
# ============================================================================

echo "=== Manna Integration Tests ==="
echo "Test directory: $TEST_DIR"
echo "Session ID: $MANNA_SESSION_ID"
echo ""

# ----------------------------------------------------------------------------
# Test 1: Init
# ----------------------------------------------------------------------------
echo "Test 1: init"
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "success: true" "init returns success"
check_yaml "$output" "federation_created: true" "first init creates federation identity"
check_yaml "$output" "federation_path: .manna/federation.yaml" "init reports the durable federation path"
INIT_BOARD_ID=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
[[ "$INIT_BOARD_ID" =~ ^mb-[a-f0-9]{32}$ ]] \
    && pass "init emits a 128-bit board identity" \
    || fail "init emits a 128-bit board identity" "$INIT_BOARD_ID"
[[ -d .manna ]] && pass ".manna directory created" || fail ".manna directory created" "Directory not found"
[[ -f .manna/issues.jsonl ]] && pass "issues.jsonl created" || fail "issues.jsonl created" "File not found"
[[ -f .manna/federation.yaml ]] && pass "federation.yaml created" || fail "federation.yaml created" "File not found"

# ----------------------------------------------------------------------------
# Test 1a: canonical derived state
# ----------------------------------------------------------------------------
echo ""
echo "Test 1a: state --json"
state_output=$(MANNA_STATE_AGENT_DO=none "$MANNA_CORE" state --json --cached-drift 2>&1) || true
check_yaml "$state_output" '"success":true' "state JSON returns success"
if STATE_OUTPUT="$state_output" python3 -c '
import json, os
data = json.loads(os.environ["STATE_OUTPUT"])
required = {"all", "now", "next", "waves", "decisions", "dreams", "tracks", "peers", "coord", "drift", "federation", "git"}
assert required <= data.keys(), required - data.keys()
assert data["total"] == 0
def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)
assert not ({"claim_token_hash", "legacy_migration", "act_token", "actor"} & set(keys(data)))
'; then
    pass "state JSON exposes the full redacted board model"
else
    fail "state JSON exposes the full redacted board model" "$state_output"
fi

# ----------------------------------------------------------------------------
# Test 1b: kill-mid-init recovery
# ----------------------------------------------------------------------------
echo ""
echo "Test 1b: kill-mid-init recovery"
CRASH_INIT_DIR=$(mktemp -d)
cd "$CRASH_INIT_DIR"
git init -q
MANNA_TESTING=1 MANNA_TEST_INIT_PAUSE_BEFORE_IDENTITY_MS=30000 \
    "$MANNA_CORE" init >init.log 2>&1 &
init_pid=$!
init_prepared=0
for _ in $(seq 1 200); do
    if [[ -f .manna/transactions/board-init.yaml ]] \
        && [[ -f .manna/issues.jsonl ]] \
        && [[ -f .manna/workflow.yaml ]] \
        && [[ ! -e .manna/board.yaml ]]; then
        init_prepared=1
        break
    fi
    if ! kill -0 "$init_pid" 2>/dev/null; then
        break
    fi
    sleep 0.05
done
if [[ "$init_prepared" -eq 1 ]]; then
    pass "init reaches a journaled pre-identity state"
else
    fail "init reaches a journaled pre-identity state" "$(cat init.log 2>/dev/null || true)"
fi
kill -KILL "$init_pid" 2>/dev/null || true
wait "$init_pid" 2>/dev/null || true
[[ ! -e .manna/board.yaml ]] && pass "killed init never publishes partial identity" || fail "killed init never publishes partial identity" "board identity exists"
[[ -f .manna/transactions/board-init.yaml ]] && pass "killed init retains authenticated recovery intent" || fail "killed init retains authenticated recovery intent" "journal missing"

output=$("$MANNA_CORE" init 2>&1) || true
check_yaml "$output" "success: true" "rerun recovers killed init"
check_yaml "$output" "recovered_transactions: 1" "recovered init reports its journal"
for durable in .manna/issues.jsonl .manna/sessions.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .manna/federation.yaml .handoff/README.md; do
    [[ -f "$durable" ]] && pass "recovered init publishes $durable" || fail "recovered init publishes $durable" "file missing"
done
transaction_files=$(find .manna/transactions -type f 2>/dev/null | wc -l | tr -d ' ')
check_exit 0 "$transaction_files" "init recovery directory is empty at rest"
init_state_before=$({ git hash-object .manna/issues.jsonl .manna/sessions.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .manna/federation.yaml .handoff/README.md; } | git hash-object --stdin)
output=$("$MANNA_CORE" init 2>&1) || true
check_yaml "$output" "recovered_transactions: 0" "repeated init has no recovery work"
check_yaml "$output" "federation_created: false" "repeated init preserves federation identity"
init_state_after=$({ git hash-object .manna/issues.jsonl .manna/sessions.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .manna/federation.yaml .handoff/README.md; } | git hash-object --stdin)
if [[ "$init_state_before" == "$init_state_after" ]]; then
    pass "repeated init is byte-stable after crash recovery"
else
    fail "repeated init is byte-stable after crash recovery" "$init_state_before -> $init_state_after"
fi
cd "$TEST_DIR"

# ----------------------------------------------------------------------------
# Test 1c: kill between workflow and federation recovery
# ----------------------------------------------------------------------------
echo ""
echo "Test 1c: kill between workflow and federation recovery"
CRASH_FEDERATION_DIR=$(mktemp -d)
cd "$CRASH_FEDERATION_DIR"
git init -q
MANNA_TESTING=1 MANNA_TEST_INIT_PAUSE_BEFORE_FEDERATION_MS=30000 \
    "$MANNA_CORE" init >init.log 2>&1 &
init_pid=$!
workflow_published=0
for _ in $(seq 1 200); do
    if [[ -f .manna/board.yaml ]] \
        && [[ -f .manna/workflow.yaml ]] \
        && [[ ! -e .manna/federation.yaml ]]; then
        workflow_published=1
        break
    fi
    if ! kill -0 "$init_pid" 2>/dev/null; then
        break
    fi
    sleep 0.05
done
if [[ "$workflow_published" -eq 1 ]]; then
    pass "init exposes a recoverable workflow-before-federation boundary"
else
    fail "init exposes a recoverable workflow-before-federation boundary" "$(cat init.log 2>/dev/null || true)"
fi
kill -KILL "$init_pid" 2>/dev/null || true
wait "$init_pid" 2>/dev/null || true
[[ ! -e .manna/federation.yaml ]] \
    && pass "killed init cannot report success without federation identity" \
    || fail "killed init cannot report success without federation identity" "manifest unexpectedly exists"
output=$("$MANNA_CORE" init 2>&1) || true
check_yaml "$output" "success: true" "rerun converges workflow and federation"
check_yaml "$output" "federation_created: true" "rerun creates the missing federation identity"
[[ -f .manna/federation.yaml ]] \
    && pass "rerun publishes federation identity" \
    || fail "rerun publishes federation identity" "manifest missing"
cd "$TEST_DIR"

# ----------------------------------------------------------------------------
# Test 2: Create issues
# ----------------------------------------------------------------------------
echo ""
echo "Test 2: create"
output=$("$MANNA" create "First issue" "Description for first issue" 2>&1) || true
check_yaml "$output" "success: true" "create returns success"
ID1=$(extract_id "$output")
[[ -n "$ID1" ]] && pass "ID extracted: $ID1" || fail "ID extraction" "Could not extract ID from output"

output=$("$MANNA" create "Second issue" 2>&1) || true
check_yaml "$output" "success: true" "create second issue"
ID2=$(extract_id "$output")
[[ -n "$ID2" ]] && pass "ID extracted: $ID2" || fail "ID extraction" "Could not extract ID"

output=$("$MANNA" create "Third issue for blocking" 2>&1) || true
ID3=$(extract_id "$output")
[[ -n "$ID3" ]] && pass "ID extracted: $ID3" || fail "ID extraction" "Could not extract ID"

# ----------------------------------------------------------------------------
# Test 3: List issues
# ----------------------------------------------------------------------------
echo ""
echo "Test 3: list"
output=$("$MANNA" list 2>&1) || true
check_yaml "$output" "success: true" "list returns success"
check_yaml "$output" "issues:" "list contains issues array"
check_yaml "$output" "$ID1" "list contains first issue"
check_yaml "$output" "$ID2" "list contains second issue"

# Test list with status filter
output=$("$MANNA" list --status open 2>&1) || true
check_yaml "$output" "success: true" "list --status open returns success"
check_yaml "$output" "status: open" "list shows open issues"

# ----------------------------------------------------------------------------
# Test 4: Show issue
# ----------------------------------------------------------------------------
echo ""
echo "Test 4: show"
output=$("$MANNA" show "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "show returns success"
check_yaml "$output" "$ID1" "show contains correct ID"
check_yaml "$output" "First issue" "show contains title"
check_yaml "$output" "Description for first issue" "show contains description"

# ----------------------------------------------------------------------------
# Test 5: Claim issue
# ----------------------------------------------------------------------------
echo ""
echo "Test 5: claim"
output=$("$MANNA" claim "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "claim returns success"
check_yaml "$output" "status: in_progress" "claim sets status to in_progress"
check_yaml "$output" "$MANNA_SESSION_ID" "claim sets claimed_by to session"

# ----------------------------------------------------------------------------
# Test 6: Status
# ----------------------------------------------------------------------------
echo ""
echo "Test 6: status"
output=$("$MANNA" status 2>&1) || true
check_yaml "$output" "success: true" "status returns success"
check_yaml "$output" "$MANNA_SESSION_ID" "status shows session ID"
check_yaml "$output" "$ID1" "status shows claimed issue"

# ----------------------------------------------------------------------------
# Test 7: Block
# ----------------------------------------------------------------------------
echo ""
echo "Test 7: block"
output=$("$MANNA" block "$ID2" "$ID3" 2>&1) || true
check_yaml "$output" "success: true" "block returns success"
check_yaml "$output" "status: blocked" "block sets status to blocked"
check_yaml "$output" "$ID3" "block shows blocker ID"

# Verify blocked issue shows in list
output=$("$MANNA" list --status blocked 2>&1) || true
check_yaml "$output" "$ID2" "blocked issue appears in filtered list"

# ----------------------------------------------------------------------------
# Test 8: Unblock
# ----------------------------------------------------------------------------
echo ""
echo "Test 8: unblock"
output=$("$MANNA" unblock "$ID2" "$ID3" 2>&1) || true
check_yaml "$output" "success: true" "unblock returns success"
check_yaml "$output" "status: open" "unblock reverts status to open"

# ----------------------------------------------------------------------------
# Test 9: Done
# ----------------------------------------------------------------------------
echo ""
echo "Test 9: done"
output=$("$MANNA" done "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "done returns success"
check_yaml "$output" "status: done" "done sets status to done"
check_released "$output" "done reports an empty release list without dependents"

# Verify done issue shows in list
output=$("$MANNA" list --status done 2>&1) || true
check_yaml "$output" "$ID1" "done issue appears in filtered list"

# ----------------------------------------------------------------------------
# Test 10: Abandon
# ----------------------------------------------------------------------------
echo ""
echo "Test 10: abandon"
# First claim ID2
"$MANNA" claim "$ID2" >/dev/null 2>&1 || true
output=$("$MANNA" abandon "$ID2" 2>&1) || true
check_yaml "$output" "success: true" "abandon returns success"
check_yaml "$output" "status: open" "abandon reverts status to open"

# ----------------------------------------------------------------------------
# Test 11: Context
# ----------------------------------------------------------------------------
echo ""
echo "Test 11: context"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "success: true" "context returns success"
check_yaml "$output" "context:" "context contains context field"
check_yaml "$output" "Manna Context" "context contains header"

# Test with max-tokens
output=$("$MANNA" context --max-tokens 100 2>&1) || true
check_yaml "$output" "success: true" "context with max-tokens returns success"

# ============================================================================
# Edge Case Tests
# ============================================================================

echo ""
echo "=== Edge Case Tests ==="

# ----------------------------------------------------------------------------
# Test E1: Claim already-claimed issue
# ----------------------------------------------------------------------------
echo ""
echo "Test E1: claim already-claimed issue"
"$MANNA" claim "$ID3" >/dev/null 2>&1 || true  # First claim

# Try to claim from different session
export MANNA_SESSION_ID="ses_other_$$"
output=$("$MANNA" claim "$ID3" 2>&1) || exit_code=$?
if [[ "$output" == *"success: false"* ]]; then
    pass "re-claim returns error"
else
    fail "re-claim returns error" "Expected success: false, got: $output"
fi
export MANNA_SESSION_ID="ses_test_$$"  # Restore

# ----------------------------------------------------------------------------
# Test E2: Done on non-existent ID
# ----------------------------------------------------------------------------
echo ""
echo "Test E2: done on non-existent ID"
output=$("$MANNA" done "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "done non-existent returns error"
check_yaml "$output" "not found" "error mentions not found"

# ----------------------------------------------------------------------------
# Test E3: Show non-existent ID
# ----------------------------------------------------------------------------
echo ""
echo "Test E3: show non-existent ID"
output=$("$MANNA" show "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "show non-existent returns error"

# ----------------------------------------------------------------------------
# Test E4: Invalid status filter
# ----------------------------------------------------------------------------
echo ""
echo "Test E4: invalid status filter"
output=$("$MANNA" list --status invalid 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "invalid status returns error"
check_yaml "$output" "Invalid status" "error mentions invalid status"

# ----------------------------------------------------------------------------
# Test E5: Empty title
# ----------------------------------------------------------------------------
echo ""
echo "Test E5: empty title"
output=$("$MANNA" create "" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "empty title returns error"

# ----------------------------------------------------------------------------
# Test E6: Concurrent creates
# ----------------------------------------------------------------------------
echo ""
echo "Test E6: concurrent creates (10 parallel)"
CONCURRENT_DIR=$(mktemp -d)
cd "$CONCURRENT_DIR"
"$MANNA" init >/dev/null 2>&1

# Spawn 10 parallel creates and retain each result. A failed creator is the
# primary concurrency signal; counting the board alone discards the cause.
for i in {1..10}; do
    (
        set +e
        "$MANNA" create "Concurrent issue $i" >"create.$i.out" 2>&1
        echo $? >"create.$i.rc"
        exit 0
    ) &
done
wait

create_failures=0
create_failure_details=""
for i in {1..10}; do
    if [[ "$(cat "create.$i.rc")" -ne 0 ]]; then
        create_failures=$((create_failures + 1))
        create_failure_details+="creator $i: $(tr '\n' ' ' <"create.$i.out")"$'\n'
    fi
done
if [[ "$create_failures" -eq 0 ]]; then
    pass "all concurrent create commands returned success"
else
    fail "all concurrent create commands returned success" "$create_failure_details"
fi

# Verify all 10 issues were created (no corruption)
output=$("$MANNA" list 2>&1)
count=$(echo "$output" | grep -c "mn-" || true)
if [[ "$count" -eq 10 ]]; then
    pass "all 10 concurrent creates succeeded"
else
    fail "all 10 concurrent creates succeeded" "Expected 10 issues, got $count"
fi

# Verify JSONL file is valid (no partial lines)
lines=$(wc -l < .manna/issues.jsonl | tr -d ' ')
if [[ "$lines" -eq 10 ]]; then
    pass "JSONL file has correct line count"
else
    fail "JSONL file has correct line count" "Expected 10 lines, got $lines"
fi

# Exactly one session may win a claim, and only that session may mutate it.
output=$("$MANNA" create "Atomic claim target" 2>&1)
RACE_ID=$(extract_id "$output")
for i in {1..10}; do
    (
        set +e
        MANNA_SESSION_ID="ses_racer_$i" "$MANNA" claim "$RACE_ID" >"claim.$i.out" 2>&1
        echo $? >"claim.$i.rc"
        exit 0
    ) &
done
wait
claim_winners=0
for i in {1..10}; do
    if [[ "$(cat "claim.$i.rc")" -eq 0 ]]; then
        claim_winners=$((claim_winners + 1))
    fi
done
check_exit 1 "$claim_winners" "concurrent claim has exactly one winner"
output=$("$MANNA" show "$RACE_ID" 2>&1)
RACE_OWNER=$(echo "$output" | awk '/claimed_by:/ {print $2; exit}')
intruder_exit=0
MANNA_SESSION_ID="ses_intruder" "$MANNA" done "$RACE_ID" >/dev/null 2>&1 || intruder_exit=$?
check_exit 1 "$intruder_exit" "non-owner cannot complete claimed work"
intruder_exit=0
MANNA_SESSION_ID="ses_intruder" "$MANNA" abandon "$RACE_ID" >/dev/null 2>&1 || intruder_exit=$?
check_exit 1 "$intruder_exit" "non-owner cannot abandon claimed work"
impersonator_exit=0
MANNA_SESSION_ID="$RACE_OWNER" \
MANNA_SESSION_TOKEN="wrong-owner-token-0123456789abcdef0123456789abcdef" \
    "$MANNA" done "$RACE_ID" >/dev/null 2>&1 || impersonator_exit=$?
check_exit 1 "$impersonator_exit" "owner label alone cannot impersonate the claim token"
status_exit=0
MANNA_SESSION_ID="$RACE_OWNER" "$MANNA" update "$RACE_ID" --status done >/dev/null 2>&1 || status_exit=$?
check_exit 1 "$status_exit" "update --status cannot bypass lifecycle verbs"
MANNA_SESSION_ID="$RACE_OWNER" "$MANNA" abandon "$RACE_ID" >/dev/null 2>&1

output=$("$MANNA" create "Missing identity target" 2>&1)
UNPINNED_ID=$(extract_id "$output")
unpinned_exit=0
# MANNA_OPERATOR=0: this script may run from a terminal, and a terminal is
# now an identity (the operator's). The opt-out keeps this the no-identity path.
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
    MANNA_OPERATOR=0 \
    "$MANNA" claim "$UNPINNED_ID" >/dev/null 2>&1 || unpinned_exit=$?
check_exit 2 "$unpinned_exit" "claim fails closed without a pinned session identity"

output=$("$MANNA" create "Codex host identity target" 2>&1)
CODEX_ID=$(extract_id "$output")
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="019d7912-5a47-7c01-b9ae-90ac2060a27e" \
    "$MANNA" claim "$CODEX_ID" >/dev/null 2>&1
output=$(env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="019d7912-5a47-7c01-b9ae-90ac2060a27e" \
    "$MANNA" status 2>&1)
check_yaml "$output" "codex-019d79125a477c01" "status resolves the Codex host session label"
check_yaml "$output" "$CODEX_ID" "status finds work claimed through the Codex host identity"
codex_done_exit=0
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="019d7912-5a47-7c01-b9ae-90ac2060a27e" \
    "$MANNA" done "$CODEX_ID" >/dev/null 2>&1 || codex_done_exit=$?
check_exit 0 "$codex_done_exit" "Codex thread identity survives separate claim and done invocations"

output=$("$MANNA" create "Codex host ownership target" 2>&1)
CODEX_OWNER_ID=$(extract_id "$output")
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="aaaaaaaa-1111-4222-8333-bbbbbbbbbbbb" \
    "$MANNA" claim "$CODEX_OWNER_ID" >/dev/null 2>&1
codex_intruder_exit=0
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="cccccccc-4444-4555-8666-dddddddddddd" \
    "$MANNA" done "$CODEX_OWNER_ID" >/dev/null 2>&1 || codex_intruder_exit=$?
check_exit 1 "$codex_intruder_exit" "different Codex thread cannot use another thread's claim"
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    CODEX_THREAD_ID="aaaaaaaa-1111-4222-8333-bbbbbbbbbbbb" \
    "$MANNA" abandon "$CODEX_OWNER_ID" >/dev/null 2>&1

cd "$TEST_DIR"
rm -rf "$CONCURRENT_DIR"

# ----------------------------------------------------------------------------
# Test E7: Block with non-existent blocker
# ----------------------------------------------------------------------------
echo ""
echo "Test E7: block with non-existent blocker"
output=$("$MANNA" list 2>&1)
first_id=$(extract_id "$output")
output=$("$MANNA" block "$first_id" "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "block with non-existent blocker returns error"

# ----------------------------------------------------------------------------
# Test E8: Double init
# ----------------------------------------------------------------------------
echo ""
echo "Test E8: double init (should be idempotent)"
"$MANNA" init >/dev/null 2>&1
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "success: true" "second init succeeds"

# ============================================================================
# YAML Validation
# ============================================================================

echo ""
echo "=== YAML Validation ==="

# Check if yq is available for proper YAML validation
if command -v yq &>/dev/null; then
    output=$("$MANNA" list 2>&1)
    if echo "$output" | yq eval '.' - >/dev/null 2>&1; then
        pass "list output is valid YAML (yq)"
    else
        fail "list output is valid YAML (yq)" "yq parsing failed"
    fi
    
    output=$("$MANNA" context 2>&1)
    if echo "$output" | yq eval '.' - >/dev/null 2>&1; then
        pass "context output is valid YAML (yq)"
    else
        fail "context output is valid YAML (yq)" "yq parsing failed"
    fi
else
    # Basic validation: check YAML-like structure
    output=$("$MANNA" list 2>&1)
    if [[ "$output" =~ ^success: ]] && [[ "$output" =~ issues: ]]; then
        pass "list output has YAML structure (basic check)"
    else
        fail "list output has YAML structure (basic check)" "Missing expected fields"
    fi
    
    output=$("$MANNA" context 2>&1)
    if [[ "$output" =~ ^success: ]] && [[ "$output" =~ context: ]]; then
        pass "context output has YAML structure (basic check)"
    else
        fail "context output has YAML structure (basic check)" "Missing expected fields"
    fi
fi

# ============================================================================
# Board Grammar Tests (types, tracks, dream, lint, reconcile)
# ============================================================================

echo ""
echo "=== Board Grammar Tests ==="

GRAMMAR_DIR=$(mktemp -d)
GRAMMAR_PHYS=$(cd "$GRAMMAR_DIR" && pwd -P)
cd "$GRAMMAR_DIR"
git init -q
"$MANNA" init >/dev/null 2>&1
git add -- .manna .handoff/README.md

# ----------------------------------------------------------------------------
# Test G1: types and track edges
# ----------------------------------------------------------------------------
echo ""
echo "Test G1: types and track edges"
output=$("$MANNA" create "Umbrella track" --type track 2>&1) || true
check_yaml "$output" "success: true" "create --type track succeeds"
check_yaml "$output" "type: track" "created issue carries type track"
TRACK_ID=$(extract_id "$output")

output=$("$MANNA" create "Tracked item" --track "$TRACK_ID" --source "test/integration.sh" 2>&1) || true
check_yaml "$output" "success: true" "create --track succeeds"
check_yaml "$output" "track: $TRACK_ID" "created item carries track edge"
check_yaml "$output" "source: test/integration.sh" "created item carries source"
ITEM_ID=$(extract_id "$output")

output=$("$MANNA" create "Bad edge" --track "$ITEM_ID" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "--track to a non-track errors"
check_yaml "$output" "not a track" "error names the non-track target"

output=$("$MANNA" create "Ghost edge" --track "mn-404404" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "--track to a missing id errors"

output=$("$MANNA" create "Nested track" --type track --track "$TRACK_ID" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "tracks don't nest on create"

output=$("$MANNA" update "$ITEM_ID" --type track 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "update --type track with a track edge errors"

output=$("$MANNA" list --type track 2>&1) || true
check_yaml "$output" "$TRACK_ID" "list --type track finds the track"
if [[ "$output" != *"$ITEM_ID"* ]]; then
    pass "list --type track excludes items"
else
    fail "list --type track excludes items" "item leaked into track filter: $output"
fi

output=$("$MANNA" list --track "$TRACK_ID" 2>&1) || true
check_yaml "$output" "$ITEM_ID" "list --track finds track members"

# ----------------------------------------------------------------------------
# Test G2: dream walks up to the nearest board
# ----------------------------------------------------------------------------
echo ""
echo "Test G2: dream on local board"
mkdir -p "$GRAMMAR_DIR/sub/dir"
cd "$GRAMMAR_DIR/sub/dir"
output=$("$MANNA" dream "A spark from below" --source "shower" 2>&1) || true
check_yaml "$output" "success: true" "dream succeeds from a subdirectory"
check_yaml "$output" "type: dream" "dream carries type dream"
check_yaml "$output" "board: $GRAMMAR_PHYS" "dream walked up to the nearest board"
DREAM_ID=$(extract_id "$output")
cd "$GRAMMAR_DIR"
output=$("$MANNA" show "$DREAM_ID" 2>&1) || true
check_yaml "$output" "A spark from below" "dream landed on the walk-up board"

# ----------------------------------------------------------------------------
# Test G2b: dream carries its substance in --description
# ----------------------------------------------------------------------------
echo ""
echo "Test G2b: dream --description"
output=$("$MANNA" dream "Titled spark" --description "The full substance of the idea lives here, not in the title." 2>&1) || true
check_yaml "$output" "success: true" "dream with --description succeeds"
DESC_DREAM_ID=$(extract_id "$output")
output=$("$MANNA" show "$DESC_DREAM_ID" 2>&1) || true
check_yaml "$output" "The full substance of the idea lives here" "dream description landed on the row"

long_spark=$(printf 'x%.0s' $(seq 1 501))
output=$("$MANNA" dream "$long_spark" 2>&1) || true
check_yaml "$output" "success: false" "oversized spark is refused"
check_yaml "$output" "put the substance in --description" "oversized spark error teaches the split"

# ----------------------------------------------------------------------------
# Test G3: dream global inbox fallback
# ----------------------------------------------------------------------------
echo ""
echo "Test G3: dream global inbox fallback"
INBOX_HOME=$(mktemp -d)
NOBOARD_DIR=$(mktemp -d)
cd "$NOBOARD_DIR"
output=$(AGENT_DO_HOME="$INBOX_HOME" "$MANNA" dream "Homeless spark" 2>&1) || true
check_yaml "$output" "success: true" "dream succeeds with no board in sight"
check_yaml "$output" "filed to global inbox" "dream reports the inbox fallback"
if [[ -f "$INBOX_HOME/inbox/.manna/issues.jsonl" ]]; then
    pass "inbox board auto-initialized"
else
    fail "inbox board auto-initialized" "no issues.jsonl under $INBOX_HOME/inbox/.manna"
fi
INBOX_BOARD_ID=$(awk '/board_id:/ {print $2; exit}' "$INBOX_HOME/inbox/.manna/federation.yaml" 2>/dev/null || true)
[[ "$INBOX_BOARD_ID" =~ ^mb-[a-f0-9]{32}$ ]] \
    && pass "inbox board auto-enrolls in federation" \
    || fail "inbox board auto-enrolls in federation" "$INBOX_BOARD_ID"
cd "$GRAMMAR_DIR"
rm -rf "$INBOX_HOME" "$NOBOARD_DIR"

# ----------------------------------------------------------------------------
# Test G4: lint gate
# ----------------------------------------------------------------------------
echo ""
echo "Test G4: lint"
# Board so far: track + tracked item + open dream (untracked dreams are fine)
"$MANNA" sync >/dev/null 2>&1
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint exits 0 on a clean board"
check_yaml "$output" "clean: true" "lint reports clean"

output=$("$MANNA" create "Loose item" 2>&1) || true
LOOSE_ID=$(extract_id "$output")
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint exits 1 with findings"
check_yaml "$output" "untracked_item" "lint names the untracked_item rule"
check_yaml "$output" "$LOOSE_ID" "lint names the loose item"

"$MANNA" update "$LOOSE_ID" --track "$TRACK_ID" >/dev/null 2>&1 || true
"$MANNA" sync >/dev/null 2>&1
lint_exit=0
output=$("$MANNA" lint --json 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint exits 0 after attaching the item"
check_yaml "$output" '"clean":true' "lint --json reports clean"

# ----------------------------------------------------------------------------
# Test G5: reconcile
# ----------------------------------------------------------------------------
echo ""
echo "Test G5: reconcile"
# Completion releases dependents inline, with no intervening reconcile or sync.
output=$("$MANNA" create "Blocker work" --track "$TRACK_ID" 2>&1) || true
A_ID=$(extract_id "$output")
output=$("$MANNA" create "Dependent work" --track "$TRACK_ID" 2>&1) || true
B_ID=$(extract_id "$output")
output=$("$MANNA" create "Second blocker work" --track "$TRACK_ID" 2>&1) || true
C_ID=$(extract_id "$output")
output=$("$MANNA" create "Dependent with two blockers" --track "$TRACK_ID" 2>&1) || true
D_ID=$(extract_id "$output")
"$MANNA" block "$B_ID" "$A_ID" >/dev/null 2>&1
"$MANNA" block "$D_ID" "$A_ID" >/dev/null 2>&1
"$MANNA" block "$D_ID" "$C_ID" >/dev/null 2>&1
"$MANNA" claim "$A_ID" >/dev/null 2>&1
done_exit=0
output=$("$MANNA" done "$A_ID" 2>&1) || done_exit=$?
check_exit 0 "$done_exit" "done with dependents exits 0"
check_released "$output" "done lists only the fully released dependent" "$B_ID"
output=$("$MANNA" show "$B_ID" 2>&1) || true
check_yaml "$output" "status: open" "done immediately opens its single dependent"
check_yaml "$output" "blocked_by: []" "done removes the completed blocker edge"
output=$("$MANNA" show "$D_ID" 2>&1) || true
check_yaml "$output" "status: blocked" "two-blocker dependent stays blocked after the first done"
if ISSUE_OUTPUT="$output" python3 - "$C_ID" <<'PY'
import os, sys, yaml
assert yaml.safe_load(os.environ['ISSUE_OUTPUT'])['issue']['blocked_by'] == [sys.argv[1]]
PY
then
    pass "only the unfinished blocker remains on the dependent"
else
    fail "only the unfinished blocker remains on the dependent" "$output"
fi
claim_exit=0
"$MANNA" claim "$B_ID" >/dev/null 2>&1 || claim_exit=$?
check_exit 0 "$claim_exit" "released dependent is immediately claimable"
"$MANNA" abandon "$B_ID" >/dev/null 2>&1
"$MANNA" claim "$C_ID" >/dev/null 2>&1
done_exit=0
output=$("$MANNA" done "$C_ID" 2>&1) || done_exit=$?
check_exit 0 "$done_exit" "last blocker completion exits 0"
check_released "$output" "last blocker done lists the newly released dependent" "$D_ID"
output=$("$MANNA" show "$D_ID" 2>&1) || true
check_yaml "$output" "status: open" "two-blocker dependent opens after both complete"
check_yaml "$output" "blocked_by: []" "both completed blocker edges are removed"

# Deliberately hand-edit this isolated fixture to emulate an older binary's
# stale board. Reconcile must still repair it, although current done cannot
# produce the desync through the normal lifecycle path.
python3 - "$B_ID" "$A_ID" <<'PY'
import json, pathlib, sys
path = pathlib.Path('.manna/issues.jsonl')
rows = [json.loads(line) for line in path.read_text().splitlines()]
dependent = next(row for row in rows if row['id'] == sys.argv[1])
dependent['status'] = 'blocked'
dependent['blocked_by'] = [sys.argv[2]]
path.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
PY
"$MANNA" sync >/dev/null 2>&1

rec_exit=0
output=$("$MANNA" reconcile 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile exits 0 (advisory)"
check_yaml "$output" "blocker_desync" "reconcile detects the blocker desync"
check_yaml "$output" "$B_ID" "reconcile names the desynced issue"

output=$("$MANNA" show "$B_ID" 2>&1) || true
check_yaml "$output" "status: blocked" "reconcile without --fix mutates nothing"

rec_exit=0
output=$("$MANNA" reconcile --write-drift 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile --write-drift exits 0"
if [[ -f .manna/drift.yaml ]]; then
    pass "drift.yaml written"
else
    fail "drift.yaml written" "missing .manna/drift.yaml"
fi
if command -v yq &>/dev/null; then
    if yq eval '.' .manna/drift.yaml >/dev/null 2>&1; then
        pass "drift.yaml is valid YAML (yq)"
    else
        fail "drift.yaml is valid YAML (yq)" "yq parsing failed"
    fi
fi
if grep -q "generated_at:" .manna/drift.yaml && grep -q "findings:" .manna/drift.yaml; then
    pass "drift.yaml has the pinned shape"
else
    fail "drift.yaml has the pinned shape" "missing generated_at/findings keys"
fi
if grep -q "kind: blocker_desync" .manna/drift.yaml; then
    pass "drift.yaml carries the finding"
else
    fail "drift.yaml carries the finding" "no blocker_desync entry"
fi

OUTSIDE_DRIFT=$(mktemp)
printf 'outside sentinel\n' > "$OUTSIDE_DRIFT"
rm -f .manna/drift.yaml
ln -s "$OUTSIDE_DRIFT" .manna/drift.yaml
drift_symlink_exit=0
output=$("$MANNA" reconcile --write-drift 2>&1) || drift_symlink_exit=$?
check_exit 2 "$drift_symlink_exit" "drift writer rejects a symlinked destination"
check_yaml "$output" "refusing symlinked" "drift refusal names the filesystem boundary"
if [[ "$(cat "$OUTSIDE_DRIFT")" == "outside sentinel" ]]; then
    pass "drift symlink refusal leaves the outside file untouched"
else
    fail "drift symlink refusal leaves the outside file untouched" "outside file changed"
fi
rm -f .manna/drift.yaml "$OUTSIDE_DRIFT"

rec_exit=0
output=$("$MANNA" reconcile --fix 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile --fix exits 0"
output=$("$MANNA" show "$B_ID" 2>&1) || true
check_yaml "$output" "status: open" "reconcile --fix unblocked the dependent"

output=$("$MANNA" reconcile --dream-age-days 0 --json 2>&1) || true
check_yaml "$output" "stale_dream" "reconcile --dream-age-days 0 flags the fresh dream"

# ----------------------------------------------------------------------------
# Test G6: context renders the track tree (and stays v1 without tracks)
# ----------------------------------------------------------------------------
echo ""
echo "Test G6: context track tree"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "## Umbrella track ($TRACK_ID)" "context groups items under the track"
check_yaml "$output" "## Dreams" "context renders a Dreams section"
check_yaml "$output" "$DREAM_ID" "context lists the dream"
if [[ "$output" != *"$A_ID"* ]]; then
    pass "context still excludes done issues"
else
    fail "context still excludes done issues" "done issue leaked: $output"
fi
if [[ "$output" != *"## Open Issues"* ]]; then
    pass "track tree replaces the by-status sections"
else
    fail "track tree replaces the by-status sections" "v1 sections leaked into grouped render"
fi

UNTYPED_DIR=$(mktemp -d)
cd "$UNTYPED_DIR"
"$MANNA" init >/dev/null 2>&1
"$MANNA" create "Plain issue" >/dev/null 2>&1
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "## Open Issues (1)" "untyped board keeps the v1 render"
if [[ "$output" != *"## Untracked"* && "$output" != *"## Dreams"* ]]; then
    pass "untyped board has no tree sections"
else
    fail "untyped board has no tree sections" "tree sections leaked: $output"
fi
cd "$GRAMMAR_DIR"
rm -rf "$UNTYPED_DIR"

cd "$TEST_DIR"
rm -rf "$GRAMMAR_DIR"

# ----------------------------------------------------------------------------
# Test G5b: reconcile --fix cures a landed, orphaned-proof claim (mn-ba8db6)
# ----------------------------------------------------------------------------
echo ""
echo "Test G5b: landed_open --fix closes orphaned in_progress claims"
WEDGE_DIR=$(mktemp -d)
cd "$WEDGE_DIR"
git init -q
git -c user.email=manna@test -c user.name=manna-test commit -q --allow-empty -m "root"
"$MANNA" init >/dev/null 2>&1
output=$("$MANNA" create "Wedged work" 2>&1) || true
WEDGE_ID=$(extract_id "$output")
MANNA_SESSION_ID="ses_wedge_$$" MANNA_SESSION_TOKEN="wedge-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
    "$MANNA" claim "$WEDGE_ID" >/dev/null 2>&1

# The owner's process "restarts": same visible label, different secret.
done_exit=0
MANNA_SESSION_ID="ses_wedge_$$" MANNA_SESSION_TOKEN="wedge-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" \
    "$MANNA" done "$WEDGE_ID" >/dev/null 2>&1 || done_exit=$?
if [[ $done_exit -ne 0 ]]; then
    pass "done refuses a mismatched ownership proof"
else
    fail "done refuses a mismatched ownership proof" "done succeeded with the wrong secret"
fi

# The work verifiably landed: a commit carries the Manna trailer.
git -c user.email=manna@test -c user.name=manna-test commit -q --allow-empty -m "fix: shipped

Manna: $WEDGE_ID"

output=$("$MANNA" reconcile 2>&1) || true
check_yaml "$output" "landed_open" "reconcile sees the landed evidence"

# The owner cures its own claim by presenting the VERIFIED proof (label
# alone is spoofable and never bypasses the liveness guard). The verified
# path needs no coord lookup, so this holds in any environment; the
# lost-proof path rides coord liveness and is covered at the unit level.
output=$(MANNA_SESSION_ID="ses_wedge_$$" MANNA_SESSION_TOKEN="wedge-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
    "$MANNA" reconcile --fix 2>&1) || true
check_yaml "$output" "closed on landed evidence" "reconcile --fix closes on the receipt"
output=$("$MANNA" show "$WEDGE_ID" 2>&1) || true
check_yaml "$output" "status: done" "wedged item is done after the cure"
"$MANNA" sync >/dev/null 2>&1

# Unclaimed landed_open stays advisory — merge judgment stays human.
output=$("$MANNA" create "Advisory work" 2>&1) || true
ADVIS_ID=$(extract_id "$output")
git -c user.email=manna@test -c user.name=manna-test commit -q --allow-empty -m "notes

Manna: $ADVIS_ID"
output=$("$MANNA" reconcile --fix 2>&1) || true
output=$("$MANNA" show "$ADVIS_ID" 2>&1) || true
check_yaml "$output" "status: open" "unclaimed landed_open stays advisory"

# ----------------------------------------------------------------------------
# Test G5d: done closes on landed evidence (mn-4061c8)
# ----------------------------------------------------------------------------
echo ""
echo "Test G5d: done closes on landed evidence"
# A filing-chore trailer (board files only) is not evidence: the advisory
# item above carries one, and a stranger's done still needs a claim.
chore_exit=0
MANNA_SESSION_ID="ses_stranger_$$" MANNA_SESSION_TOKEN="stranger-token-cccccccccccccccccccccccccccccccc" \
    "$MANNA" done "$ADVIS_ID" >/dev/null 2>&1 || chore_exit=$?
check_exit 1 "$chore_exit" "a trailer on an empty commit is not evidence"

# The work lands: a commit carrying the trailer touches source. Anyone with an
# identity may then close; the evidence authorizes, never the requester.
output=$("$MANNA" create "Evidence work" 2>&1) || true
EVIDENCE_ID=$(extract_id "$output")
MANNA_SESSION_ID="ses_builder_$$" MANNA_SESSION_TOKEN="builder-token-dddddddddddddddddddddddddddddddd" \
    "$MANNA" claim "$EVIDENCE_ID" >/dev/null 2>&1
printf 'shipped\n' > src.txt
git add src.txt
git -c user.email=manna@test -c user.name=manna-test commit -q -m "feat: shipped

Manna: $EVIDENCE_ID"
EVIDENCE_SHA=$(git rev-parse HEAD)
output=$(MANNA_SESSION_ID="ses_stranger_$$" MANNA_SESSION_TOKEN="stranger-token-cccccccccccccccccccccccccccccccc" \
    "$MANNA" done "$EVIDENCE_ID" 2>&1) || true
check_yaml "$output" "success: true" "a stranger closes a landed item on evidence"
check_yaml "$output" "authority: evidence" "the close names evidence as its authority"
check_yaml "$output" "$EVIDENCE_SHA" "the close cites the landed commit"
check_yaml "$output" "claimed_by: ses_builder_$$" "the builder's claim stays as history"
output=$("$MANNA" show "$EVIDENCE_ID" 2>&1) || true
check_yaml "$output" "status: done" "landed item is done"

# The wrong checkout names the right board instead of failing on identity.
ELSEWHERE_DIR=$(mktemp -d)
(cd "$ELSEWHERE_DIR" && git init -q && "$MANNA" init >/dev/null 2>&1)
output=$(cd "$ELSEWHERE_DIR" && env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
    -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
    MANNA_OPERATOR=0 "$MANNA" done "$EVIDENCE_ID" 2>&1) || true
check_yaml "$output" "not found" "a foreign id is reported as not found before identity is demanded"
rm -rf "$ELSEWHERE_DIR"

# ----------------------------------------------------------------------------
# Test G5e: the operator's terminal is an identity
# ----------------------------------------------------------------------------
echo ""
echo "Test G5e: operator identity from a terminal"
if [[ "$(uname -s)" == "Darwin" ]] && command -v script >/dev/null 2>&1; then
    output=$("$MANNA" create "Operator work" 2>&1) || true
    OPERATOR_ID=$(extract_id "$output")
    MANNA_SESSION_ID="ses_gone_$$" MANNA_SESSION_TOKEN="gone-token-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" \
        "$MANNA" claim "$OPERATOR_ID" >/dev/null 2>&1
    # script(1) lends the command a pseudo-terminal, which is what a human's
    # shell has and an agent's pipe does not.
    output=$(script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" done "$OPERATOR_ID" 2>&1 </dev/null) || true
    check_yaml "$output" "authority: operator" "the operator closes over a stranded claim from a terminal"
    output=$("$MANNA" show "$OPERATOR_ID" 2>&1) || true
    check_yaml "$output" "status: done" "operator-closed item is done"
else
    echo "  - skipped: needs macOS script(1) to lend a pseudo-terminal"
fi

# ----------------------------------------------------------------------------
# Test G5c: machine-key derived identity survives a process restart
# ----------------------------------------------------------------------------
echo ""
echo "Test G5c: derived identity survives restart"
DERIVE_HOME=$(mktemp -d)
RESTART_UUID="0f0f0f0f-1111-2222-3333-444444444444"
output=$("$MANNA" create "Derived identity work" 2>&1) || true
DERIVE_ID=$(extract_id "$output")
env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN AGENT_DO_HOME="$DERIVE_HOME" \
    CLAUDE_SESSION_ID="$RESTART_UUID" "$MANNA" claim "$DERIVE_ID" >/dev/null 2>&1
# "Restart": a fresh process presents only the same host session id. The
# blanked pair proves empty-means-unset (how hooks neutralize stale pins).
done_exit=0
MANNA_SESSION_ID= MANNA_SESSION_TOKEN= AGENT_DO_HOME="$DERIVE_HOME" \
    CLAUDE_SESSION_ID="$RESTART_UUID" "$MANNA" done "$DERIVE_ID" >/dev/null 2>&1 || done_exit=$?
check_exit 0 "$done_exit" "derived proof re-derives after restart; done succeeds"
"$MANNA" sync >/dev/null 2>&1

# ----------------------------------------------------------------------------
# Test G7: strict workflow pairing, claim gate, sprawl detection, legacy compatibility
# ----------------------------------------------------------------------------
echo ""
echo "Test G7: strict Manna and handoff workflow"
PAIR_DIR=$(mktemp -d)
cd "$PAIR_DIR"
git init -q
printf '.handoff/\n.manna/\n' > .gitignore
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: strict" "new board enables the strict workflow"
check_yaml "$output" "gitignore_updated: true" "init repairs a local .handoff ignore rule"
[[ -f .manna/workflow.yaml ]] && pass "init creates .manna/workflow.yaml" || fail "init creates .manna/workflow.yaml" "File not found"
[[ -f .manna/board.yaml ]] && pass "init pins strict board identity separately" || fail "init pins strict board identity separately" "File not found"
[[ -f .manna/handoff-order.yaml ]] && pass "init creates board-owned handoff priority" || fail "init creates board-owned handoff priority" "File not found"
[[ -f .handoff/README.md ]] && pass "init creates .handoff/README.md" || fail "init creates .handoff/README.md" "File not found"
ignore_exit=0
git check-ignore --quiet -- .handoff/README.md || ignore_exit=$?
check_exit 1 "$ignore_exit" ".handoff is durable Git-visible state"
ignore_exit=0
git check-ignore --quiet -- .manna/workflow.yaml || ignore_exit=$?
check_exit 1 "$ignore_exit" ".manna is durable Git-visible state"
ignore_exit=0
git check-ignore --quiet -- .manna/issues.jsonl || ignore_exit=$?
check_exit 1 "$ignore_exit" "issues.jsonl is durable Git-visible state"

lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint distinguishes Git-visible from Git-tracked board state"
check_yaml "$output" "workflow_tracking" "lint classifies untracked durable state"
check_yaml "$output" "git-tracked: no" "lint reports the durable tracking predicate"
check_yaml "$output" ".manna/issues.jsonl" "lint names the untracked canonical board"
git add -- .manna .handoff/README.md

output=$("$MANNA" create "Paired work" 2>&1) || true
check_yaml "$output" "success: true" "create generates a paired item"
PAIR_ID=$(extract_id "$output")
PROMPT_A=".handoff/$PAIR_ID-paired-work.md"

output=$("$MANNA" show "$PAIR_ID" 2>&1) || true
check_yaml "$output" "prompt: $PROMPT_A" "show displays the prompt pointer"
[[ -f "$PROMPT_A" ]] && pass "create writes the canonical handoff" || fail "create writes the canonical handoff" "File not found"
claim_count=$(grep -c "agent-do manna claim $PAIR_ID" "$PROMPT_A" || true)
check_exit 1 "$claim_count" "handoff carries exactly one claim command"
check_yaml "$(sed -n '1,14p' "$PROMPT_A")" "base_commit:" "handoff binds its base commit"
check_yaml "$(sed -n '1,14p' "$PROMPT_A")" "binding: sha256:" "handoff carries its content binding"

output=$("$MANNA" sync 2>&1) || true
check_yaml "$output" "renamed: 1" "sync derives the first numbered handoff"
PROMPT_A=".handoff/01-$PAIR_ID-paired-work.md"
output=$("$MANNA" show "$PAIR_ID" 2>&1) || true
check_yaml "$output" "prompt: $PROMPT_A" "sync transaction repoints the board"
[[ -f "$PROMPT_A" ]] && pass "sync installs the numbered handoff" || fail "sync installs the numbered handoff" "File not found"

rm -f .manna/workflow.yaml
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "deleting workflow.yaml cannot downgrade a strict board"
check_yaml "$output" "strict Manna board identity exists" "claim names the missing strict config"
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "restored_config: true" "init restores the independently pinned strict config"
[[ -f .manna/workflow.yaml ]] && pass "restored strict config exists" || fail "restored strict config exists" "File not found"

printf '.manna/issues.jsonl\n' >> .gitignore
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "claim fails when issues.jsonl is hidden from Git"
check_yaml "$output" "issues.jsonl is ignored" "claim names the hidden board file"
printf '!.manna/issues.jsonl\n' >> .gitignore

OUTSIDE_HANDOFF=$(mktemp -d)
ln -s "$OUTSIDE_HANDOFF" .handoff/escape
create_exit=0
output=$("$MANNA" create "Symlink escape" --prompt .handoff/escape/work.md 2>&1) || create_exit=$?
check_exit 1 "$create_exit" "strict create rejects a symlink escape"
check_yaml "$output" "crosses a symlink" "symlink refusal names the filesystem boundary"
rm -f .handoff/escape
rm -rf "$OUTSIDE_HANDOFF"

printf '\nSealed continuation context.\n' >> "$PROMPT_A"
claim_exit=0
"$MANNA" claim "$PAIR_ID" >/dev/null 2>&1 || claim_exit=$?
check_exit 2 "$claim_exit" "unsealed handoff edits block claim"
output=$("$MANNA" handoff seal "$PAIR_ID" 2>&1) || true
check_yaml "$output" "success: true" "handoff seal binds an intentional edit"
claim_exit=0
"$MANNA" claim "$PAIR_ID" >/dev/null 2>&1 || claim_exit=$?
check_exit 0 "$claim_exit" "sealed handoff becomes claimable"
# An edit after claim without resealing is paperwork drift: the close on the
# owner's proof still lands, and the response carries the stale seal as a
# warning (mn-4061c8). A second paired item keeps PAIR_ID live for the
# metadata trap below.
output=$("$MANNA" create "Stale seal close" 2>&1) || true
STALE_ID=$(extract_id "$output")
"$MANNA" sync >/dev/null 2>&1 || true
STALE_PROMPT=$("$MANNA" show "$STALE_ID" | awk -F': ' '/^  prompt:/ {print $2; exit}')
"$MANNA" claim "$STALE_ID" >/dev/null 2>&1
printf '\nEdited after claim without resealing.\n' >> "$STALE_PROMPT"
done_exit=0
output=$("$MANNA" done "$STALE_ID" 2>&1) || done_exit=$?
check_exit 0 "$done_exit" "done closes a handoff edited after claim"
check_yaml "$output" "warnings:" "done carries the drift as a warning"
check_yaml "$output" "binding is stale" "done names the stale handoff seal"
output=$("$MANNA" show "$STALE_ID" 2>&1) || true
check_yaml "$output" "status: done" "warned close is done"
# Seal the late edit and move the completed handoff to its history name so
# the board below stays presentation-clean for the lint and reconcile gates.
"$MANNA" handoff seal "$STALE_ID" >/dev/null 2>&1 || true
"$MANNA" sync >/dev/null 2>&1 || true
"$MANNA" handoff seal "$PAIR_ID" >/dev/null 2>&1 || true
"$MANNA" abandon "$PAIR_ID" >/dev/null 2>&1

printf '\nUnsealed metadata trap.\n' >> "$PROMPT_A"
before_title=$("$MANNA" show "$PAIR_ID" | awk -F': ' '/title:/ {print $2; exit}')
update_exit=0
output=$("$MANNA" update "$PAIR_ID" --title "Should not bless body" 2>&1) || update_exit=$?
check_exit 2 "$update_exit" "metadata update cannot silently seal handoff edits"
check_yaml "$output" "unsealed" "metadata refusal names the seal boundary"
after_title=$("$MANNA" show "$PAIR_ID" | awk -F': ' '/title:/ {print $2; exit}')
if [[ "$before_title" == "$after_title" ]]; then
    pass "failed metadata update leaves the board row unchanged"
else
    fail "failed metadata update leaves the board row unchanged" "$before_title -> $after_title"
fi
"$MANNA" handoff seal "$PAIR_ID" >/dev/null 2>&1

printf '\nTampered while config is absent.\n' >> "$PROMPT_A"
digest_before=$("$MANNA" show "$PAIR_ID" | awk '/handoff_digest:/ {print $2; exit}')
rm -f .manna/workflow.yaml
restore_exit=0
output=$("$MANNA" init 2>&1) || restore_exit=$?
check_exit 2 "$restore_exit" "workflow restoration refuses an unsealed handoff"
check_yaml "$output" "invalid handoff" "restoration reports the unsealed pair"
digest_after=$("$MANNA" show "$PAIR_ID" | awk '/handoff_digest:/ {print $2; exit}')
if [[ "$digest_before" == "$digest_after" ]]; then
    pass "workflow restoration does not rewrite the board seal"
else
    fail "workflow restoration does not rewrite the board seal" "$digest_before -> $digest_after"
fi
"$MANNA" handoff seal "$PAIR_ID" >/dev/null 2>&1

before_rows=$(wc -l < .manna/issues.jsonl | tr -d ' ')
before_handoffs=$(find .handoff -name 'mn-*.md' -type f | wc -l | tr -d ' ')
printf '.handoff/mn-*.md\n' >> .gitignore
create_exit=0
output=$("$MANNA" create "Ignored handoff" 2>&1) || create_exit=$?
check_exit 2 "$create_exit" "create fails when a generated handoff would be ignored"
after_rows=$(wc -l < .manna/issues.jsonl | tr -d ' ')
after_handoffs=$(find .handoff -name 'mn-*.md' -type f | wc -l | tr -d ' ')
if [[ "$before_rows" == "$after_rows" && "$before_handoffs" == "$after_handoffs" ]]; then
    pass "failed create rolls back both sides of the pair"
else
    fail "failed create rolls back both sides of the pair" "rows $before_rows->$after_rows, handoffs $before_handoffs->$after_handoffs"
fi
printf '!.handoff/mn-*.md\n' >> .gitignore

lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint accepts the generated pair"

rec_exit=0
output=$("$MANNA" reconcile --json 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile remains advisory on a paired board"
if [[ "$output" != *"prompt_pairing"* && "$output" != *"workflow_sprawl"* ]]; then
    pass "generated pair reports no linkage or sprawl drift"
else
    fail "generated pair reports no linkage or sprawl drift" "unexpected finding: $output"
fi

create_exit=0
output=$("$MANNA" create "Wrong root" --prompt .handoffs/wrong.md 2>&1) || create_exit=$?
check_exit 1 "$create_exit" "strict create rejects a parallel handoff root"

sed -i.bak "s/agent-do manna claim $PAIR_ID/agent-do manna claim mn-dead00/" "$PROMPT_A"
rm -f "$PROMPT_A.bak"
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "claim fails closed on a broken handoff link"
check_yaml "$output" "Refusing claim" "claim explains the broken handoff contract"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint fails on a mismatched claim command"
check_yaml "$output" "handoff_contract" "lint names the handoff contract"
sed -i.bak "s/agent-do manna claim mn-dead00/agent-do manna claim $PAIR_ID/" "$PROMPT_A"
rm -f "$PROMPT_A.bak"
"$MANNA" handoff seal "$PAIR_ID" >/dev/null 2>&1

mkdir -p .handoffs
printf 'agent-do manna claim %s\n' "$PAIR_ID" > .handoffs/shadow.md
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "workflow_sprawl" "reconcile detects a shadow handoff root"
check_yaml "$output" ".handoffs" "sprawl finding names the shadow root"
sprawl_exit=0
"$MANNA" reconcile --json >/dev/null 2>&1 || sprawl_exit=$?
check_exit 1 "$sprawl_exit" "shadow handoff roots make reconcile fail"

DEEP_SHADOW=.dev/one/two/three/four/five/six/seven/eight/nine/ten/eleven/twelve
mkdir -p "$DEEP_SHADOW"
cp "$PROMPT_A" "$DEEP_SHADOW/deep-shadow.md"
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "deep-shadow.md" "sprawl scan has no nesting ceiling"

LINK_TARGET=$(mktemp)
cp "$PROMPT_A" "$LINK_TARGET"
mkdir -p .dev/linked
ln -s "$LINK_TARGET" .dev/linked/shadow.md
output=$("$MANNA" reconcile --json 2>&1) || true
# A symlink is never followed: an alias of outside content is not a tracked
# work-order surface, and an internal alias points at files the walk already
# sees by their real path (mn-4061c8).
if [[ "$output" != *".dev/linked/shadow.md"* ]]; then
    pass "sprawl scan never follows a symlinked file"
else
    fail "sprawl scan never follows a symlinked file" "$output"
fi
rm -f "$LINK_TARGET"

printf 'agent-do manna claim %s\n' "$PAIR_ID" > neutral-notes.md
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "neutral-notes.md" "generic claim-bearing Markdown is a shadow workflow"
rm -f neutral-notes.md

NEUTRAL_TARGET=$(mktemp -d)
printf 'agent-do manna claim %s\n' "$PAIR_ID" > "$NEUTRAL_TARGET/work.md"
ln -s "$NEUTRAL_TARGET" resources
output=$("$MANNA" reconcile --json 2>&1) || true
if [[ "$output" != *"resources"* ]]; then
    pass "neutral external symlink directories are skipped"
else
    fail "neutral external symlink directories are skipped" "$output"
fi
# A handoff-shaped alias is the one symlink that is reported: board-level,
# without an item, so it informs and never holds one item's claim.
ln -s "$NEUTRAL_TARGET" handoff-mirror
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "handoff-mirror" "a handoff-shaped symlink root is reported"
check_yaml "$output" '{"kind":"workflow_sprawl","detail":"symlinked shadow handoff root is forbidden","evidence":"./handoff-mirror"' "the handoff-shaped alias finding carries no item"
rm -f handoff-mirror resources
rm -rf "$NEUTRAL_TARGET"

LEGACY_DIR=$(mktemp -d)
LEGACY_PHYS=$(cd "$LEGACY_DIR" && pwd -P)
cd "$LEGACY_DIR"
git init -q
mkdir -p .manna
touch .manna/sessions.jsonl
printf '%s\n' '{"id":"mn-a1b2c3","title":"Existing legacy row","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[]}' > .manna/issues.jsonl
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: legacy" "init classifies a real pre-workflow board explicitly"
check_yaml "$(cat .manna/board.yaml)" "workflow: legacy" "legacy mode is pinned instead of inferred"
git add -- .manna
mkdir -p .dev/session-prompts
LEGACY_PROMPT="$LEGACY_PHYS/.dev/session-prompts/lane-a.md"
output=$("$MANNA" create "Legacy paired work" --prompt "$LEGACY_PROMPT" 2>&1) || true
check_yaml "$output" "success: true" "existing legacy boards retain explicit prompt pointers"
LEGACY_ID=$(extract_id "$output")
printf 'agent-do manna claim %s\n' "$LEGACY_ID" > "$LEGACY_PROMPT"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "legacy prompt pairing remains valid"

cd "$TEST_DIR"
rm -rf "$PAIR_DIR"
rm -rf "$LEGACY_DIR"

# ----------------------------------------------------------------------------
# Test G7b: journaled migration unlocks a partially initialized legacy board
# ----------------------------------------------------------------------------
echo ""
echo "Test G7b: legacy board migration"
MIGRATION_DIR=$(mktemp -d)
cd "$MIGRATION_DIR"
git init -q
printf '.handoff/\n.manna/\n' > .gitignore
mkdir -p .manna .handoff
touch .manna/sessions.jsonl
printf 'Legacy research context.\n' > .handoff/legacy-research.md
printf '%s\n' \
    '{"id":"mn-a10001","title":"Legacy track","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"type":"track"}' \
    '{"id":"mn-a10002","title":"Unpaired active item","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"track":"mn-a10001"}' \
    '{"id":"mn-a10003","title":"Blocked unpaired item","status":"blocked","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":["mn-a10002"],"track":"mn-a10001"}' \
    '{"id":"mn-a10004","title":"Legacy claim without proof","status":"in_progress","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"claimed_by":"legacy-session","claimed_at":"2026-01-02T00:00:00Z","track":"mn-a10001"}' \
    '{"id":"mn-a10005","title":"Historical item","status":"done","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"claimed_by":"legacy-history","claimed_at":"2026-01-02T00:00:00Z","track":"mn-a10001","prompt":".dev/session-prompts/deleted.md"}' \
    '{"id":"mn-a10006","title":"Parked dream","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"type":"dream","track":"mn-a10001"}' \
    > .manna/issues.jsonl

write_exit=0
output=$("$MANNA" create "Must migrate first" 2>&1) || write_exit=$?
check_exit 2 "$write_exit" "identityless nonempty board refuses ordinary writes"
check_yaml "$output" "nonempty legacy board" "identityless error classifies the board"
check_yaml "$output" "agent-do manna migrate" "identityless error names the convergence command"
if [[ "$output" != *"agent-do manna init"* ]]; then
    pass "identityless legacy guidance does not misroute to init"
else
    fail "identityless legacy guidance does not misroute to init" "$output"
fi

output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: legacy" "legacy .handoff content does not imply strict board identity"
check_yaml "$output" "federation_created: true" "legacy init enrolls the existing board"
LEGACY_FEDERATION_ID=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
[[ "$LEGACY_FEDERATION_ID" =~ ^mb-[a-f0-9]{32}$ ]] \
    && pass "legacy init emits a valid board identity" \
    || fail "legacy init emits a valid board identity" "$LEGACY_FEDERATION_ID"
rm -f .handoff/legacy-research.md

# Reproduce the Stage 0 partial state: identity was published before the old
# rows had authoritative pairs, so init restores scaffolding and then fails.
printf 'version: 1\nworkflow: strict\n' > .manna/board.yaml
init_exit=0
output=$("$MANNA" init 2>&1) || init_exit=$?
check_exit 2 "$init_exit" "partial strict identity reproduces the legacy-board write lock"
check_yaml "$output" "missing its authoritative handoff pair" "init names the unpaired legacy row"

output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "success: true" "migrate admits the legacy board"
check_yaml "$output" "migrated: true" "first migration reports a state change"
check_yaml "$output" "paired_items: 3" "migration generates every active item handoff"
check_yaml "$output" "historical_rows: 1" "migration grandfathers done history"
check_yaml "$output" "exempt_rows: 2" "migration exempts tracks and dreams"
check_yaml "$output" "released_claims: 2" "migration releases unauthenticated legacy claims"
check_yaml "$output" "federation_created: false" "migration preserves the identity created by legacy init"
check_yaml "$output" "board_id: $LEGACY_FEDERATION_ID" "migration reports the preserved board identity"
[[ ! -e .manna/transactions/legacy-board-migration.yaml ]] && pass "migration journal retires after commit" || fail "migration journal retires after commit" "journal still exists"
handoff_count=$(find .handoff -maxdepth 1 -name 'mn-*.md' -type f | wc -l | tr -d ' ')
check_exit 3 "$handoff_count" "migration creates exactly one unnumbered handoff per active item"
check_yaml "$(cat .manna/board.yaml)" "migrated_from_legacy_at:" "strict identity records legacy admission"

output=$("$MANNA" show mn-a10004 2>&1) || true
check_yaml "$output" "status: open" "legacy in-progress claim returns to open"
check_yaml "$output" "released_claimed_by: legacy-session" "released owner remains auditable"
output=$("$MANNA" show mn-a10005 2>&1) || true
check_yaml "$output" "disposition: history" "done row is marked as grandfathered history"
check_yaml "$output" "previous_prompt: .dev/session-prompts/deleted.md" "historical pointer is retained as annotation"
if [[ "$output" != *$'\nprompt:'* ]]; then
    pass "dead historical pointer is no longer authoritative"
else
    fail "dead historical pointer is no longer authoritative" "$output"
fi
output=$("$MANNA" show mn-a10006 2>&1) || true
check_yaml "$output" "disposition: exempt" "dream remains exempt from handoff pairing"

migration_state_before=$({ git hash-object .manna/issues.jsonl; find .handoff -maxdepth 1 -name '*-mn-*.md' -type f | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "migrated: false" "second migration is an idempotent no-op"
migration_state_after=$({ git hash-object .manna/issues.jsonl; find .handoff -maxdepth 1 -name '*-mn-*.md' -type f | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
if [[ "$migration_state_before" == "$migration_state_after" ]]; then
    pass "idempotent migration preserves board and handoff bytes"
else
    fail "idempotent migration preserves board and handoff bytes" "$migration_state_before -> $migration_state_after"
fi

output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: strict" "init succeeds after migration"
output=$("$MANNA" update mn-a10002 --description "Writable after migration" 2>&1) || true
check_yaml "$output" "success: true" "metadata writes work after migration"
claim_exit=0
"$MANNA" claim mn-a10002 >/dev/null 2>&1 || claim_exit=$?
check_exit 0 "$claim_exit" "claim works after migration"
done_exit=0
"$MANNA" done mn-a10002 >/dev/null 2>&1 || done_exit=$?
check_exit 0 "$done_exit" "done works after migration"
"$MANNA" sync >/dev/null 2>&1
git add -- .manna .handoff/README.md
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "migrated fixture has no lint findings"

cd "$TEST_DIR"
rm -rf "$MIGRATION_DIR"

# ----------------------------------------------------------------------------
# Test G7c: a v2 create on a legacy board still has one-command convergence
# ----------------------------------------------------------------------------
echo ""
echo "Test G7c: mixed legacy and strict board migration"
MIXED_DIR=$(mktemp -d)
cd "$MIXED_DIR"
git init -q
printf '.handoff/\n.manna/\n' > .gitignore
mkdir -p .manna .handoff/campaigns
touch .manna/sessions.jsonl
printf '%s\n' \
    '{"id":"mn-b20001","title":"Legacy first priority","status":"in_progress","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"claimed_by":"legacy-pid-owner","claimed_at":"2026-01-02T00:00:00Z","prompt":".handoff/01-mn-b20001-legacy-first-priority.md"}' \
    '{"id":"mn-b20002","title":"Legacy blocked priority","status":"blocked","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":["mn-b20001"],"prompt":".handoff/02b01-mn-b20002-legacy-blocked-priority.md"}' \
    '{"id":"mn-b20003","title":"Legacy completed history","status":"done","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"claimed_by":"legacy-history","claimed_at":"2026-01-02T00:00:00Z","prompt":".dev/session-prompts/deleted.md"}' \
    > .manna/issues.jsonl
printf '# Legacy first\n\nPreserve alpha work-order content exactly.\n' > .handoff/01-mn-b20001-legacy-first-priority.md
printf '# Legacy blocked\n\nPreserve beta work-order content exactly.\n' > .handoff/02b01-mn-b20002-legacy-blocked-priority.md

# Reproduce the reachable production state: a strict marker exists over old
# rows, init restores the v2 scaffold but cannot finish, and v2 create still
# adds one fully sealed pair before migration runs.
printf 'version: 1\nworkflow: strict\n' > .manna/board.yaml
init_exit=0
"$MANNA" init >/dev/null 2>&1 || init_exit=$?
check_exit 2 "$init_exit" "mixed fixture reproduces the partial strict init failure"
output=$("$MANNA" create "Strict native campaign" --prompt .handoff/campaigns/strict-native.md 2>&1) || true
check_yaml "$output" "success: true" "v2 create produces the strict side of a mixed board"
MIXED_STRICT_ID=$(extract_id "$output")
MIXED_STRICT_LINE_BEFORE=$(grep -F "\"id\":\"$MIXED_STRICT_ID\"" .manna/issues.jsonl)
MIXED_STRICT_HASH_BEFORE=$(git hash-object .handoff/campaigns/strict-native.md)

output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "success: true" "migrate converges a mixed board"
check_yaml "$output" "migrated: true" "mixed migration reports a state change"
check_yaml "$output" "paired_items: 2" "mixed migration adopts only the two legacy active items"
check_yaml "$output" "historical_rows: 1" "mixed migration grandfathers legacy history"
check_yaml "$output" "released_claims: 2" "mixed migration releases only unauthenticated legacy claims"
check_yaml "$output" "federation_created: true" "direct migration enrolls the existing board"
MIXED_FEDERATION_ID=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
[[ "$MIXED_FEDERATION_ID" =~ ^mb-[a-f0-9]{32}$ ]] \
    && pass "direct migration emits a valid board identity" \
    || fail "direct migration emits a valid board identity" "$MIXED_FEDERATION_ID"
MIXED_STRICT_LINE_AFTER=$(grep -F "\"id\":\"$MIXED_STRICT_ID\"" .manna/issues.jsonl)
MIXED_STRICT_HASH_AFTER=$(git hash-object .handoff/campaigns/strict-native.md)
if [[ "$MIXED_STRICT_LINE_BEFORE" == "$MIXED_STRICT_LINE_AFTER" && "$MIXED_STRICT_HASH_BEFORE" == "$MIXED_STRICT_HASH_AFTER" ]]; then
    pass "mixed migration preserves strict row and handoff bytes"
else
    fail "mixed migration preserves strict row and handoff bytes" "strict state changed during migration"
fi
grep -Fq 'Preserve alpha work-order content exactly.' .handoff/01-mn-b20001-legacy-first-priority.md \
    && pass "mixed migration preserves first legacy work order" \
    || fail "mixed migration preserves first legacy work order" "legacy content missing"
grep -Fq 'Preserve beta work-order content exactly.' .handoff/02b01-mn-b20002-legacy-blocked-priority.md \
    && pass "mixed migration preserves blocked legacy work order" \
    || fail "mixed migration preserves blocked legacy work order" "legacy content missing"
check_yaml "$(cat .manna/handoff-order.yaml)" "- mn-b20001" "unique handmade prefixes seed first-class priority"

mixed_state_before=$({ git hash-object .manna/issues.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .manna/federation.yaml .handoff/README.md; find .handoff -type f -name '*.md' ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "migrated: false" "second mixed migration is an idempotent no-op"
check_yaml "$output" "federation_created: false" "second mixed migration preserves federation identity"
mixed_state_after=$({ git hash-object .manna/issues.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .manna/federation.yaml .handoff/README.md; find .handoff -type f -name '*.md' ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
if [[ "$mixed_state_before" == "$mixed_state_after" ]]; then
    pass "second mixed migration preserves every durable byte"
else
    fail "second mixed migration preserves every durable byte" "$mixed_state_before -> $mixed_state_after"
fi
transaction_files=$(find .manna/transactions -type f 2>/dev/null | wc -l | tr -d ' ')
check_exit 0 "$transaction_files" "mixed migration recovery directory is empty at rest"

sync_exit=0
output=$("$MANNA" sync 2>&1) || sync_exit=$?
check_exit 0 "$sync_exit" "sync converges adopted and strict handoff names"
check_yaml "$output" "changed: true" "sync reports mixed presentation convergence"
[[ -f .handoff/01-mn-b20001-legacy-first-priority.md ]] \
    && pass "seeded first priority remains dense" \
    || fail "seeded first priority remains dense" "expected first handoff missing"
[[ -f .handoff/02b01-mn-b20002-legacy-blocked-priority.md ]] \
    && pass "blocked marker is re-derived from board edges" \
    || fail "blocked marker is re-derived from board edges" "expected blocked handoff missing"
strict_sync_count=$(find .handoff -maxdepth 1 -type f -name "03-$MIXED_STRICT_ID-*.md" | wc -l | tr -d ' ')
check_exit 1 "$strict_sync_count" "strict native handoff joins the generated dense plan"
git add -- .manna .handoff/README.md
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "synchronized mixed fixture has no lint findings"

cd "$TEST_DIR"
rm -rf "$MIXED_DIR"

# ----------------------------------------------------------------------------
# Test G7e: strict-lookalike and cross-project legacy sources converge
# ----------------------------------------------------------------------------
echo ""
echo "Test G7e: legacy source ingestion"
ADOPTION_DIR=$(mktemp -d)
ADOPTION_EXTERNAL_DIR=$(mktemp -d)
ADOPTION_EXTERNAL_SOURCE="$ADOPTION_EXTERNAL_DIR/cross-project-work-order.md"
cd "$ADOPTION_DIR"
git init -q
printf '.manna/\n' > .gitignore
mkdir -p .manna .handoff .dev/session-prompts
touch .manna/sessions.jsonl
ADOPTION_PROJECT_SOURCE="$ADOPTION_DIR/.dev/session-prompts/in-project-work-order.md"
printf '%s\n' \
    '{"id":"mn-b30001","title":"Partial frontmatter work order","status":"open","source":"estate sweep fixture","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[],"prompt":".handoff/partial-lookalike.md"}' \
    "{\"id\":\"mn-b30002\",\"title\":\"Cross-project absolute pointer\",\"status\":\"open\",\"created_at\":\"2026-01-01T00:00:00Z\",\"updated_at\":\"2026-01-01T00:00:00Z\",\"blocked_by\":[],\"prompt\":\"$ADOPTION_EXTERNAL_SOURCE\"}" \
    "{\"id\":\"mn-b30003\",\"title\":\"In-project absolute pointer\",\"status\":\"open\",\"description\":\"PROMPT: $ADOPTION_PROJECT_SOURCE — ratified design; read before starting\",\"created_at\":\"2026-01-01T00:00:00Z\",\"updated_at\":\"2026-01-01T00:00:00Z\",\"blocked_by\":[]}" \
    > .manna/issues.jsonl
cat > .handoff/partial-lookalike.md <<'EOF'
---
manna: mn-b30001
track: null
source: estate sweep fixture
---

# Existing partial work order

## Claim

```bash
agent-do manna claim mn-b30001
```

Preserve the strict-lookalike body exactly.
EOF
printf '# Cross-project work order\n\nPreserve external content exactly.\n' > "$ADOPTION_EXTERNAL_SOURCE"
printf '# In-project work order\n\nagent-do manna claim mn-b30003\n\nPreserve local content exactly.\n' > "$ADOPTION_PROJECT_SOURCE"
ADOPTION_PROJECT_HASH=$(git hash-object "$ADOPTION_PROJECT_SOURCE")

adoption_exit=0
output=$("$MANNA" migrate 2>&1) || adoption_exit=$?
check_exit 0 "$adoption_exit" "migrate ingests strict-lookalike and absolute legacy sources"
check_yaml "$output" "paired_items: 3" "source-ingestion migration pairs every active row"
partial_adopted=$(grep -rl '^manna: mn-b30001$' .handoff | head -1)
external_adopted=$(grep -rl '^manna: mn-b30002$' .handoff | head -1)
project_adopted=$(grep -rl '^manna: mn-b30003$' .handoff | head -1)
grep -Fq 'Preserve the strict-lookalike body exactly.' "$partial_adopted" \
    && pass "partial frontmatter body survives canonical wrapping" \
    || fail "partial frontmatter body survives canonical wrapping" "legacy body missing"
partial_claim_count=$(grep -c '^agent-do manna claim mn-b30001$' "$partial_adopted")
check_exit 2 "$partial_claim_count" "preserved legacy Claim text is not mistaken for canonical authority"
grep -Fq 'Preserve external content exactly.' "$external_adopted" \
    && pass "cross-project work-order content is imported" \
    || fail "cross-project work-order content is imported" "external content missing"
grep -Fq "> Legacy migration source: \"$ADOPTION_EXTERNAL_SOURCE\"" "$external_adopted" \
    && pass "cross-project provenance records the original absolute path" \
    || fail "cross-project provenance records the original absolute path" "provenance note missing"
grep -Fq 'Preserve local content exactly.' "$project_adopted" \
    && pass "absolute in-project work-order content is imported" \
    || fail "absolute in-project work-order content is imported" "local content missing"
grep -Fq '> Legacy migration source: ".dev/session-prompts/in-project-work-order.md"' "$project_adopted" \
    && pass "in-project provenance is normalized to a repository-relative path" \
    || fail "in-project provenance is normalized to a repository-relative path" "normalized note missing"
grep -Fq '"previous_prompt":".dev/session-prompts/in-project-work-order.md"' .manna/issues.jsonl \
    && pass "board annotation stores normalized in-project provenance" \
    || fail "board annotation stores normalized in-project provenance" "annotation stayed absolute"
[[ -f "$ADOPTION_EXTERNAL_SOURCE" ]] \
    && pass "cross-project source remains owned by its original project" \
    || fail "cross-project source remains owned by its original project" "external source was moved"
[[ ! -e "$ADOPTION_PROJECT_SOURCE" ]] \
    && pass "in-project shadow work order is retired transactionally" \
    || fail "in-project shadow work order is retired transactionally" "source still exists"
ADOPTION_ARCHIVE=$(find .handoff/.archive/legacy-sources -type f -name '*.source' | head -1)
adoption_archive_count=$(find .handoff/.archive/legacy-sources -type f -name '*.source' | wc -l | tr -d ' ')
check_exit 1 "$adoption_archive_count" "one imported local source produces one durable archive"
[[ -n "$ADOPTION_ARCHIVE" && "$(git hash-object "$ADOPTION_ARCHIVE")" == "$ADOPTION_PROJECT_HASH" ]] \
    && pass "legacy source archive preserves the exact imported bytes" \
    || fail "legacy source archive preserves the exact imported bytes" "archive content changed"

# Reproduce a board admitted by the preceding release, where the canonical
# pair exists but the local source was never retired. One migrate invocation
# must repair that reachable state without touching strict rows or seals.
mv "$ADOPTION_ARCHIVE" "$ADOPTION_PROJECT_SOURCE"
adoption_board_before_repair=$(git hash-object .manna/issues.jsonl)
adoption_handoffs_before_repair=$({ find .handoff -maxdepth 1 -type f -name '*.md' ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "migrated: true" "migrate repairs a previously admitted unretired source"
[[ ! -e "$ADOPTION_PROJECT_SOURCE" ]] \
    && pass "repair pass retires the resurrected shadow source" \
    || fail "repair pass retires the resurrected shadow source" "source still exists after repair"
check_exit 0 "$(find .handoff/.archive/legacy-sources -type f -name '*.source' ! -path "$ADOPTION_ARCHIVE" | wc -l | tr -d ' ')" "repair reuses the deterministic archive path"
[[ "$(git hash-object .manna/issues.jsonl)" == "$adoption_board_before_repair" ]] \
    && pass "archive-only repair preserves strict board bytes" \
    || fail "archive-only repair preserves strict board bytes" "board changed"
adoption_handoffs_after_repair=$({ find .handoff -maxdepth 1 -type f -name '*.md' ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
[[ "$adoption_handoffs_before_repair" == "$adoption_handoffs_after_repair" ]] \
    && pass "archive-only repair preserves every sealed handoff byte" \
    || fail "archive-only repair preserves every sealed handoff byte" "handoffs changed"

adoption_state_before=$({ git hash-object .manna/issues.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .handoff/README.md; find .handoff -type f ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
output=$("$MANNA" migrate 2>&1) || true
check_yaml "$output" "migrated: false" "source-ingestion migration is an idempotent no-op"
adoption_state_after=$({ git hash-object .manna/issues.jsonl .manna/board.yaml .manna/workflow.yaml .manna/handoff-order.yaml .handoff/README.md; find .handoff -type f ! -name README.md | sort | while IFS= read -r file; do git hash-object "$file"; done; } | git hash-object --stdin)
[[ "$adoption_state_before" == "$adoption_state_after" ]] \
    && pass "source-ingestion replay preserves every durable byte" \
    || fail "source-ingestion replay preserves every durable byte" "$adoption_state_before -> $adoption_state_after"
transaction_files=$(find .manna/transactions -type f 2>/dev/null | wc -l | tr -d ' ')
check_exit 0 "$transaction_files" "source-ingestion recovery directory is empty at rest"
sync_exit=0
output=$("$MANNA" sync 2>&1) || sync_exit=$?
check_exit 0 "$sync_exit" "sync converges imported source presentation"
git add -- .manna .handoff/README.md
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "imported source fixture has no lint findings"

cd "$TEST_DIR"
rm -rf "$ADOPTION_DIR" "$ADOPTION_EXTERNAL_DIR"

# ----------------------------------------------------------------------------
# Test G7d: ordered handoff presentation and live-claim rename hold
# ----------------------------------------------------------------------------
echo ""
echo "Test G7d: ordered handoff presentation"
ORDER_DIR=$(mktemp -d)
cd "$ORDER_DIR"
git init -q
"$MANNA" init >/dev/null 2>&1
git add -- .manna .handoff/README.md
output=$("$MANNA" create "First priority" 2>&1) || true
ORDER_ONE=$(extract_id "$output")
output=$("$MANNA" create "Second priority" 2>&1) || true
ORDER_TWO=$(extract_id "$output")
output=$("$MANNA" create "Third priority" 2>&1) || true
ORDER_THREE=$(extract_id "$output")

output=$("$MANNA" sync 2>&1) || true
check_yaml "$output" "renamed: 3" "one sync numbers every new work order"
[[ -f ".handoff/01-$ORDER_ONE-first-priority.md" ]] && pass "priority 01 filename is dense" || fail "priority 01 filename is dense" "missing first handoff"
[[ -f ".handoff/02-$ORDER_TWO-second-priority.md" ]] && pass "priority 02 filename is dense" || fail "priority 02 filename is dense" "missing second handoff"
[[ -f ".handoff/03-$ORDER_THREE-third-priority.md" ]] && pass "priority 03 filename is dense" || fail "priority 03 filename is dense" "missing third handoff"

"$MANNA" claim "$ORDER_TWO" >/dev/null 2>&1
"$MANNA" block "$ORDER_TWO" "$ORDER_ONE" >/dev/null 2>&1
output=$("$MANNA" sync 2>&1) || true
check_yaml "$output" "$ORDER_TWO" "sync reports a claimed handoff held from rename"
[[ -f ".handoff/02-$ORDER_TWO-second-priority.md" ]] && pass "live claim keeps its bare filename" || fail "live claim keeps its bare filename" "claimed handoff moved"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint flags filename drift held by a live claim"
check_yaml "$output" "handoff_filename" "lint names the filename rule"
reconcile_exit=0
output=$("$MANNA" reconcile --json 2>&1) || reconcile_exit=$?
check_exit 1 "$reconcile_exit" "reconcile enforces launch-gate drift"
check_yaml "$output" "handoff_presentation" "reconcile classifies presentation drift"
check_yaml "$output" "agent-do manna sync" "reconcile proposes the native repair"

abandon_exit=0
"$MANNA" abandon "$ORDER_TWO" >/dev/null 2>&1 || abandon_exit=$?
check_exit 0 "$abandon_exit" "owner can release a claimed item after it becomes blocked"
"$MANNA" sync >/dev/null 2>&1
[[ -f ".handoff/02b01-$ORDER_TWO-second-priority.md" ]] && pass "release publishes the blocker launch gate" || fail "release publishes the blocker launch gate" "b01 handoff missing"

"$MANNA" block "$ORDER_THREE" "$ORDER_ONE" >/dev/null 2>&1
"$MANNA" block "$ORDER_THREE" "$ORDER_TWO" >/dev/null 2>&1
"$MANNA" sync >/dev/null 2>&1
[[ -f ".handoff/03b02-$ORDER_THREE-third-priority.md" ]] && pass "gate selects the highest still-open blocker" || fail "gate selects the highest still-open blocker" "b02 handoff missing"

output=$("$MANNA" order "$ORDER_THREE" 1 2>&1) || true
check_yaml "$output" "success: true" "order mutates priority and synchronizes in one transaction"
[[ -f ".handoff/01b03-$ORDER_THREE-third-priority.md" ]] && pass "dependency marker re-derives after priority move" || fail "dependency marker re-derives after priority move" "01b03 handoff missing"
[[ -f ".handoff/02-$ORDER_ONE-first-priority.md" ]] && pass "priority move keeps numbering dense" || fail "priority move keeps numbering dense" "priority 02 missing"
[[ -f ".handoff/03b02-$ORDER_TWO-second-priority.md" ]] && pass "blocker chain reads through reordered names" || fail "blocker chain reads through reordered names" "03b02 handoff missing"
check_yaml "$(cat .handoff/README.md)" "| 01 | \`$ORDER_THREE\` | blocked | \`$ORDER_ONE\`, \`$ORDER_TWO\` |" "README index carries full blocker truth"
check_yaml "$(cat .manna/handoff-order.yaml)" "- $ORDER_THREE" "board file owns priority order"

state_before=$({ git hash-object .manna/issues.jsonl; git hash-object .manna/handoff-order.yaml; git hash-object .handoff/README.md; } | git hash-object --stdin)
output=$("$MANNA" sync 2>&1) || true
check_yaml "$output" "changed: false" "converged sync is idempotent"
state_after=$({ git hash-object .manna/issues.jsonl; git hash-object .manna/handoff-order.yaml; git hash-object .handoff/README.md; } | git hash-object --stdin)
if [[ "$state_before" == "$state_after" ]]; then
    pass "idempotent sync preserves board, priority, and index bytes"
else
    fail "idempotent sync preserves board, priority, and index bytes" "$state_before -> $state_after"
fi

"$MANNA" unblock "$ORDER_THREE" "$ORDER_TWO" >/dev/null 2>&1
"$MANNA" sync >/dev/null 2>&1
[[ -f ".handoff/01b02-$ORDER_THREE-third-priority.md" ]] && pass "gate updates when one blocker edge closes" || fail "gate updates when one blocker edge closes" "01b02 handoff missing"
"$MANNA" claim "$ORDER_ONE" >/dev/null 2>&1
"$MANNA" done "$ORDER_ONE" >/dev/null 2>&1
output=$("$MANNA" sync 2>&1) || true
[[ -f ".handoff/01-$ORDER_THREE-third-priority.md" ]] && pass "last closed blocker removes the launch gate" || fail "last closed blocker removes the launch gate" "bare launch handoff missing"
check_yaml "$output" "ordered_items: 2" "completed work leaves the active priority denominator"
[[ -f ".handoff/$ORDER_ONE-first-priority.md" ]] && pass "completed work returns to unnumbered history" || fail "completed work returns to unnumbered history" "historical handoff missing"
if [[ "$(cat .manna/handoff-order.yaml)" != *"$ORDER_ONE"* ]] && ! grep -qE "^\\| [0-9]{2} \\| .$ORDER_ONE. \\|" .handoff/README.md; then
    pass "completed work is absent from launch order and index"
else
    fail "completed work is absent from launch order and index" "$ORDER_ONE remains in generated launch presentation"
fi

cd "$TEST_DIR"
rm -rf "$ORDER_DIR"

# ----------------------------------------------------------------------------
# Test G8: dreams are visible and inert until converted
# ----------------------------------------------------------------------------
echo ""
echo "Test G8: dream claim gate"
GATE_DIR=$(mktemp -d)
cd "$GATE_DIR"
"$MANNA" init >/dev/null 2>&1
output=$("$MANNA" create "Umbrella track" --type track 2>&1) || true
G_TRACK=$(extract_id "$output")
output=$("$MANNA" create "Real work" --track "$G_TRACK" 2>&1) || true
G_ITEM=$(extract_id "$output")
output=$("$MANNA" dream "A parked spark" 2>&1) || true
G_DREAM=$(extract_id "$output")

# The refusal must not touch the board: hash the file on both sides.
if command -v md5 &>/dev/null; then
    hash_cmd() { md5 -q "$1"; }
else
    hash_cmd() { md5sum "$1" | awk '{print $1}'; }
fi
before_hash=$(hash_cmd .manna/issues.jsonl)
claim_exit=0
output=$("$MANNA" claim "$G_DREAM" 2>&1) || claim_exit=$?
after_hash=$(hash_cmd .manna/issues.jsonl)

check_exit 2 "$claim_exit" "claim on a dream exits 2"
check_yaml "$output" "success: false" "claim on a dream refuses"
check_yaml "$output" "$G_DREAM" "refusal names the dream id"
check_yaml "$output" "not claimable work" "refusal says a dream is not claimable work"
check_yaml "$output" "update $G_DREAM --type item" "refusal gives the exact conversion command"
check_yaml "$output" "Erik" "refusal names who authorizes"
if [[ "$before_hash" == "$after_hash" ]]; then
    pass "refused claim wrote nothing (board byte-identical)"
else
    fail "refused claim wrote nothing (board byte-identical)" "issues.jsonl changed: $before_hash -> $after_hash"
fi
output=$("$MANNA" show "$G_DREAM" 2>&1) || true
check_yaml "$output" "status: open" "refused dream is still open"
check_yaml "$output" "type: dream" "refused dream is still a dream"
if [[ "$output" != *"claimed_by"* ]]; then
    pass "refused dream carries no claim"
else
    fail "refused dream carries no claim" "claimed_by present: $output"
fi

# Visibility is the ruling: the dream stays in every list, marked inert.
output=$("$MANNA" list 2>&1) || true
check_yaml "$output" "$G_DREAM" "list still shows the dream"
check_yaml "$output" "not claimable, needs conversion" "list marks the dream inert"
output=$("$MANNA" list --json 2>&1) || true
check_yaml "$output" '"gate":"[DREAM: not claimable, needs conversion]"' "list --json carries the gate marker"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "$G_DREAM" "context still shows the dream"
# Every context row carries when it last moved, so the inert marker is pinned
# around the age rather than against a stamp that changes every second.
check_yaml "$output" "$G_DREAM: A parked spark [open] updated $(date -u +%Y-%m-%d) (" \
    "context dates and ages the dream row"
check_yaml "$output" "ago) [DREAM: not claimable, needs conversion]" \
    "context marks the dream row inert"
check_yaml "$output" "update <id> --type item" "context spells out the conversion command"

# Items are untouched by the gate.
claim_exit=0
output=$("$MANNA" claim "$G_ITEM" 2>&1) || claim_exit=$?
check_exit 0 "$claim_exit" "claim on an item still succeeds"
check_yaml "$output" "status: in_progress" "claimed item goes in_progress"
"$MANNA" abandon "$G_ITEM" >/dev/null 2>&1

# Conversion is the authorization act.
output=$("$MANNA" update "$G_DREAM" --type item 2>&1) || true
check_yaml "$output" "AUTHORIZED" "conversion prints an authorization line"
check_yaml "$output" "now claimable work" "authorization line says the row is claimable"
claim_exit=0
output=$("$MANNA" claim "$G_DREAM" 2>&1) || claim_exit=$?
check_exit 0 "$claim_exit" "claim succeeds after conversion"
check_yaml "$output" "status: in_progress" "converted dream claims like any item"

# And back: parking an item prints the inverse and restores the gate.
"$MANNA" abandon "$G_DREAM" >/dev/null 2>&1
output=$("$MANNA" update "$G_DREAM" --type dream 2>&1) || true
check_yaml "$output" "PARKED" "parking prints the inverse line"
check_yaml "$output" "no longer claimable" "inverse line says the row is not claimable"
claim_exit=0
"$MANNA" claim "$G_DREAM" >/dev/null 2>&1 || claim_exit=$?
check_exit 2 "$claim_exit" "re-parked dream refuses claim again"
output=$("$MANNA" done "$G_DREAM" 2>&1) || true
check_yaml "$output" "status: done" "done explicitly closes an unclaimed dream"

# A non-crossing edit stays silent.
output=$("$MANNA" update "$G_ITEM" --title "Real work, renamed" 2>&1) || true
if [[ "$output" != *"authorization"* ]]; then
    pass "non-crossing update prints no authorization line"
else
    fail "non-crossing update prints no authorization line" "unexpected line: $output"
fi

cd "$TEST_DIR"
rm -rf "$GATE_DIR"

# ============================================================================
# Managed lifecycle: coordinator-owned handoff and closure (mn-59f1e4)
# ============================================================================

echo ""
echo "=== Managed Lifecycle Tests ==="

# json_field <json-on-stdin> <python expr over d>
json_field() {
    python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"
}

# reviewed_submission <id>: the current submission key as the lead sees it.
reviewed_submission() {
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$1" --json 2>/dev/null | json_field 'd["submission_key"] or ""'
}
# reviewed_attempt <id>: the current attempt as the lead sees it.
reviewed_attempt() {
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$1" --json 2>/dev/null | json_field 'd["attempt"]'
}
# lead_accept <id> <check> <target> <evidence> [extra args...]: accept what the lead just reviewed.
lead_accept() {
    local id="$1" check="$2" target="$3" evidence="$4"
    shift 4
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$id" --check "$check" --target "$target" --evidence "$evidence" \
        --submission "$(reviewed_submission "$id")" --attempt "$(reviewed_attempt "$id")" "$@"
}

if [[ "$(uname -s)" == "Darwin" ]] && command -v script >/dev/null 2>&1; then
    echo ""
    echo "Test M1: worker submits, source lands elsewhere, coordinator accepts and closes without the worker"
    MANAGED_DIR=$(mktemp -d)
    cd "$MANAGED_DIR"
    git init -q -b main
    git -c user.email=manna@test -c user.name=manna-test commit -q --allow-empty -m "root"
    WORKER_ID="ses_mworker_$$"; WORKER_TOKEN="mworker-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    LEAD_ID="ses_mlead_$$";     LEAD_TOKEN="mlead-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    OTHER_ID="ses_mother_$$";   OTHER_TOKEN="mother-token-cccccccccccccccccccccccccccccccccc"
    "$MANNA" init >/dev/null 2>&1
    output=$("$MANNA" create "Managed feature" "coordinator-owned closure" 2>&1) || true
    M_ID=$(extract_id "$output")
    output=$("$MANNA" create "Depends on managed feature" "released by the managed close" 2>&1) || true
    M_DEP=$(extract_id "$output")
    "$MANNA" block "$M_DEP" "$M_ID" >/dev/null 2>&1
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file managed items"

    # The coordinator session prints its proof; the operator grants against it.
    LEAD_PROOF=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" identity --json 2>/dev/null | json_field 'd["proof"]')
    if [[ "$LEAD_PROOF" == sha256:* ]]; then
        pass "identity prints a sha256 proof, never the token"
    else
        fail "identity prints a sha256 proof, never the token" "got: $LEAD_PROOF"
    fi

    # A coordinator cannot grant itself; neither can a coord label or a worker secret.
    self_grant_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$M_ID" --reason "self" >/dev/null 2>&1 || self_grant_exit=$?
    check_exit 2 "$self_grant_exit" "a session cannot grant itself coordinator authority"

    output=$(script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$M_ID" --reason "lead for the managed feature" 2>&1 </dev/null | tr -d '\r') || true
    check_yaml "$output" "coordinator_id: $LEAD_ID" "the operator grants scoped coordinator authority"
    GRANT_ID=$(printf '%s\n' "$output" | grep -o 'grant-[0-9a-f]\{12\}' | head -1)

    # Only the grant-holder (or operator) puts the item under managed closure.
    other_require_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" \
        "$MANNA" managed require "$M_ID" --check integration >/dev/null 2>&1 || other_require_exit=$?
    check_exit 2 "$other_require_exit" "an ungranted session cannot require managed checks"
    # The same label with a different secret is not the coordinator.
    impostor_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" \
        "$MANNA" managed require "$M_ID" --check integration >/dev/null 2>&1 || impostor_exit=$?
    check_exit 2 "$impostor_exit" "the coordinator label without its proof holds no grant"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" managed require "$M_ID" --check integration --check deployed 2>&1) || true
    check_yaml "$output" "level: coordinator" "the grant-holder requires integration and deployed acceptance"

    # The worker claims and builds on a feature branch; the board checkout stays on main.
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$M_ID" >/dev/null 2>&1
    git checkout -q -b feat/managed
    printf 'feature\n' > feature.txt
    git add feature.txt
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "feat: managed feature

Manna: $M_ID"
    FEATURE_SHA=$(git rev-parse HEAD)
    git checkout -q main

    # A source-touching trailer exists, but a managed item does not close on it.
    stranger_done_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" done "$M_ID" >/dev/null 2>&1 || stranger_done_exit=$?
    check_exit 2 "$stranger_done_exit" "a trailer commit does not close a managed item for a stranger"
    git merge -q --no-ff feat/managed -m "merge managed feature into main"
    MAIN_WITH_FEATURE=$(git rev-parse HEAD)
    lead_early_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$M_ID" >/dev/null 2>&1 || lead_early_exit=$?
    check_exit 2 "$lead_early_exit" "even on HEAD, a trailer without acceptance does not close for the coordinator"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$M_ID" 2>&1) || true
    check_yaml "$output" "no submission for attempt 1" "the refusal names the missing submission"

    # reconcile --fix sees landed_open on HEAD and refuses to close a managed item.
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" reconcile --fix 2>&1) || true
    check_yaml "$output" "landed_open" "reconcile sees the landed trailer on the board checkout"
    check_yaml "$output" "is a managed item" "reconcile --fix refuses to close a managed item on a trailer"
    output=$("$MANNA" show "$M_ID" 2>&1) || true
    check_yaml "$output" "status: in_progress" "the managed item is still in progress after reconcile --fix"

    # Submission is the worker's; a stranger cannot submit, and it is not acceptance.
    printf 'Built the feature. cargo test: ok. Left: nothing.\n' > report.md
    stranger_submit_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" submit "$M_ID" --report report.md >/dev/null 2>&1 || stranger_submit_exit=$?
    check_exit 1 "$stranger_submit_exit" "a stranger cannot submit for the claim-holder"
    output=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$M_ID" --report report.md --revision "$FEATURE_SHA" 2>&1) || true
    check_yaml "$output" "status: submitted" "the worker submits its report for attempt 1"
    output=$("$MANNA" show "$M_ID" 2>&1) || true
    check_yaml "$output" "status: in_progress" "submission leaves the item in progress"

    # Integration lands on a branch the board checkout is not on.
    git branch staging "$MAIN_WITH_FEATURE"
    git checkout -q -b scratch main
    printf 'unrelated\n' > scratch.txt
    git add scratch.txt
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "scratch: board checkout moves on"
    # The board checkout is `scratch` now; staging is where the work integrated.

    # The read-only assessment pins the target explicitly and never checks out or fetches.
    assess_json=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$M_ID" --target staging --json 2>/dev/null)
    if [[ "$(printf '%s' "$assess_json" | json_field 'd["closable"]')" == "False" ]]; then
        pass "assess reports not closable before acceptance"
    else
        fail "assess reports not closable before acceptance" "$assess_json"
    fi
    if [[ "$(printf '%s' "$assess_json" | json_field 'd["integration_target"]["kind"]')" == "local_branch" ]]; then
        pass "assess classifies the target as a local branch"
    else
        fail "assess classifies the target as a local branch" "$assess_json"
    fi
    if [[ "$(printf '%s' "$assess_json" | json_field 'd["integration_target"]["is_current_head"]')" == "False" ]]; then
        pass "assess distinguishes the target from the checkout's HEAD"
    else
        fail "assess distinguishes the target from the checkout's HEAD" "$assess_json"
    fi
    if [[ "$(printf '%s' "$assess_json" | json_field '[c["relation"] for c in d["trailer_commits"] if c["sha"]=="'"$FEATURE_SHA"'"][0]')" == "in_target" ]]; then
        pass "assess finds the trailer commit inside the integration target"
    else
        fail "assess finds the trailer commit inside the integration target" "$assess_json"
    fi
    if [[ "$(printf '%s' "$assess_json" | json_field 'd["authority"]["level"]')" == "coordinator" ]]; then
        pass "assess names the caller's authority"
    else
        fail "assess names the caller's authority" "$assess_json"
    fi
    bad_target=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$M_ID" --target origin/nowhere --json 2>/dev/null | json_field 'd["integration_target"]["error"] is not None and d["closable"] is False')
    if [[ "$bad_target" == "True" ]]; then
        pass "an unavailable target fails clearly and is never closable"
    else
        fail "an unavailable target fails clearly and is never closable" "$bad_target"
    fi

    # Acceptance: granted coordinator only, at an explicitly pinned target.
    other_accept_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" \
        "$MANNA" accept "$M_ID" --check integration --target staging --evidence "merged" --submission "$(reviewed_submission "$M_ID")" --attempt 1 >/dev/null 2>&1 || other_accept_exit=$?
    check_exit 2 "$other_accept_exit" "an ungranted session cannot record acceptance"
    worker_accept_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" \
        "$MANNA" accept "$M_ID" --check integration --target staging --evidence "I say so" --submission "$(reviewed_submission "$M_ID")" --attempt 1 >/dev/null 2>&1 || worker_accept_exit=$?
    check_exit 2 "$worker_accept_exit" "the worker cannot accept its own submission"
    output=$(lead_accept $M_ID integration staging "merge $FEATURE_SHA reachable from staging" 2>&1) || true
    check_yaml "$output" "check: integration" "the coordinator accepts integration at the pinned target"
    check_yaml "$output" "kind: local_branch" "the pinned target records how the reference resolved"
    wrong_target_exit=0
    lead_accept $M_ID deployed scratch "deploy 1" >/dev/null 2>&1 || wrong_target_exit=$?
    check_exit 1 "$wrong_target_exit" "acceptance at a different target than the pinned one is refused"
    partial_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$M_ID" >/dev/null 2>&1 || partial_exit=$?
    check_exit 2 "$partial_exit" "one outstanding check still blocks closure"
    output=$(lead_accept $M_ID deployed staging "release 7 serves $MAIN_WITH_FEATURE" 2>&1) || true
    check_yaml "$output" "check: deployed" "the coordinator accepts deployment"

    # The assessment digest guards the close against a stale look.
    ASSESSMENT=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$M_ID" --json 2>/dev/null | json_field 'd["assessment"]')
    stale_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$M_ID" --assessment assess:0000 >/dev/null 2>&1 || stale_exit=$?
    check_exit 2 "$stale_exit" "a stale assessment digest refuses the close"
    stranger_final_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" done "$M_ID" --assessment "$ASSESSMENT" >/dev/null 2>&1 || stranger_final_exit=$?
    check_exit 2 "$stranger_final_exit" "a stranger cannot close even with a current assessment"

    # The worker is gone: nothing below resumes or impersonates it.
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$M_ID" --assessment "$ASSESSMENT" 2>&1) || true
    check_yaml "$output" "authority: coordinator" "the coordinator closes on recorded acceptance"
    check_yaml "$output" "status: done" "the managed item is done"
    check_yaml "$output" "claimed_by: $WORKER_ID" "the worker's claim stays as history"
    check_yaml "$output" "released:" "the close releases dependents in the same write"
    output=$("$MANNA" show "$M_DEP" 2>&1) || true
    check_yaml "$output" "status: open" "the dependent is open after the managed close"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed history "$M_ID" --json 2>/dev/null | json_field '",".join(e["action"] for e in d["events"])')
    if [[ "$output" == "require,claim,submit,accept,accept,close" ]]; then
        pass "the lifecycle audit holds the whole story in order"
    else
        fail "the lifecycle audit holds the whole story in order" "got: $output"
    fi
    if [[ -f .manna/lifecycle.jsonl && -f .manna/managed.json && -f .manna/coordinators.json ]]; then
        pass "lifecycle records live in durable sidecar files"
    else
        fail "lifecycle records live in durable sidecar files" "$(ls .manna)"
    fi
    "$MANNA" sync >/dev/null 2>&1
    git add -A >/dev/null 2>&1
    lint_exit=0
    lint_output=$("$MANNA" lint 2>&1) || lint_exit=$?
    if [[ "$lint_exit" -eq 0 ]]; then
        pass "tracked sidecars pass lint"
    else
        fail "tracked sidecars pass lint" "$lint_output"
    fi
    state_managed=$("$MANNA" state --json 2>/dev/null | json_field '[r["managed"]["attempt"] for r in d["all"] if r["id"]=="'"$M_ID"'"][0]')
    if [[ "$state_managed" == "1" ]]; then
        pass "manna state carries the managed summary for human-facing consumers"
    else
        fail "manna state carries the managed summary for human-facing consumers" "got: $state_managed"
    fi

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M2: release needs a verified stop or an isolated checkout; superseded worker; changed target"
    # Manna reaches coord through agent-do on PATH; the repo root carries both.
    export PATH="$SCRIPT_DIR/../../..:$PATH"
    COORD="$SCRIPT_DIR/../../agent-coord"
    output=$("$MANNA" create "Managed rework" "worker goes missing" 2>&1) || true
    R_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file rework"
    output=$(script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$R_ID" --reason "lead for rework" 2>&1 </dev/null | tr -d '\r') || true
    check_yaml "$output" "success: true" "the operator grants the rework item"
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$R_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$R_ID" >/dev/null 2>&1
    printf 'half done\n' > half.md
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$R_ID" --report half.md >/dev/null 2>&1
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed correct "$R_ID" --reason "tests missing" 2>&1) || true
    check_yaml "$output" "status: correction_requested" "the coordinator requests a correction"
    corr_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$R_ID" >/dev/null 2>&1 || corr_exit=$?
    check_exit 2 "$corr_exit" "a requested correction blocks closure"

    # No coord peer for the worker: liveness unknown, and unknown is not death.
    unknown_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$R_ID" --reason "worker vanished" 2>&1) || unknown_exit=$?
    check_exit 2 "$unknown_exit" "release refuses while the worker's liveness is unknown"
    check_yaml "$output" "not a verified stop" "the refusal says what would count"

    # The worker's coord presence ages into `stale` while its process is alive:
    # an old lease is not death, and the release still refuses.
    AGENT_DO_COORD_SESSION="$WORKER_ID" AGENT_DO_COORD_ACTIVE_SECONDS=1 "$COORD" touch --json >/dev/null 2>&1
    sleep 2
    stale_status=$(AGENT_DO_COORD_SESSION="$LEAD_ID" AGENT_DO_COORD_IDLE_SECONDS=0 "$COORD" peers --all --json 2>/dev/null | json_field '[p["status"] for p in d["peers"] if p["agent_id"].startswith("session-sesmworker")][0]')
    if [[ "$stale_status" == "stale" ]]; then
        pass "coord classifies the live worker's aged lease as stale"
    else
        fail "coord classifies the live worker's aged lease as stale" "got: $stale_status"
    fi
    stale_exit=0
    output=$(AGENT_DO_COORD_IDLE_SECONDS=0 MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$R_ID" --reason "looks old" 2>&1) || stale_exit=$?
    check_exit 2 "$stale_exit" "a stale lease on a live process does not authorize release"
    check_yaml "$output" "liveness is \`stale\`" "the refusal names the stale verdict and its source"
    output=$(AGENT_DO_COORD_IDLE_SECONDS=0 MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$R_ID" --json 2>/dev/null | json_field 'd["claimant"]["status"] + "/" + str(d["claimant"]["verified_gone"]) + "/" + d["claimant"]["source"]')
    if [[ "$output" == "stale/False/agent-do coord peers --json" ]]; then
        pass "assess reports liveness with its source and says stale is not verified gone"
    else
        fail "assess reports liveness with its source and says stale is not verified gone" "got: $output"
    fi

    # Isolation is validated, never taken on a name.
    other_release_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" managed release "$R_ID" --reason "mine now" --isolated-checkout "$MANAGED_DIR" >/dev/null 2>&1 || other_release_exit=$?
    check_exit 2 "$other_release_exit" "an ungranted session cannot release a managed claim"
    missing_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$R_ID" --reason "replacement" --isolated-checkout "$MANAGED_DIR-nowhere" >/dev/null 2>&1 || missing_exit=$?
    check_exit 1 "$missing_exit" "a nonexistent isolated checkout is refused"
    same_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$R_ID" --reason "replacement" --isolated-checkout "$MANAGED_DIR" 2>&1) || same_exit=$?
    check_exit 1 "$same_exit" "this checkout is not an isolated checkout"
    check_yaml "$output" "resolves to this checkout" "the refusal names the shared working tree"
    REPLACEMENT_TREE="$MANAGED_DIR-replacement"
    git worktree add -q "$REPLACEMENT_TREE" -b replacement HEAD >/dev/null 2>&1
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$R_ID" --reason "worker session unreachable; replacement works in its own tree" --isolated-checkout "$REPLACEMENT_TREE" 2>&1) || true
    check_yaml "$output" "attempt: 2" "release into a real separate working tree advances the attempt"
    check_yaml "$output" "basis: isolated_checkout" "release records its basis"
    check_yaml "$output" "isolation_toplevel:" "release records the validated toplevel"
    check_yaml "$output" "claim_release: released" "the two-phase release completed"
    check_yaml "$output" "status: open" "the released item is open for a replacement"

    # A verified stop: the worker's own session retires through coord.
    output=$("$MANNA" create "Managed stop" "worker retires" 2>&1) || true
    S_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file stop item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$S_ID" --reason "lead for stop item" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$S_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$S_ID" >/dev/null 2>&1
    AGENT_DO_COORD_SESSION="$WORKER_ID" "$COORD" stop --note "lane ended" --json >/dev/null 2>&1
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$S_ID" --reason "worker retired" 2>&1) || true
    check_yaml "$output" "basis: coord_dead" "a coord-verified stop releases without isolation"
    check_yaml "$output" "worker_liveness: stopped" "the release records the verified verdict"

    # The superseded worker cannot submit or close; the replacement starts attempt 2.
    old_submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$R_ID" --report half.md >/dev/null 2>&1 || old_submit_exit=$?
    check_exit 1 "$old_submit_exit" "the superseded worker cannot submit"
    old_done_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" done "$R_ID" >/dev/null 2>&1 || old_done_exit=$?
    check_exit 2 "$old_done_exit" "the superseded worker cannot close"
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" claim "$R_ID" >/dev/null 2>&1
    printf 'redone with tests\n' > redone.md
    output=$(MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" submit "$R_ID" --report redone.md 2>&1) || true
    check_yaml "$output" "attempt: 2" "the replacement submits for attempt 2"
    lead_accept $R_ID integration HEAD "reviewed" >/dev/null 2>&1
    # A changed target after acceptance makes the recorded acceptance stop counting.
    printf 'moved\n' > moved.txt
    git add moved.txt
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "scratch: head moves"
    moved=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$R_ID" --target HEAD --json 2>/dev/null | json_field 'd["integration_target"]["matches_pinned"]')
    if [[ "$moved" == "False" ]]; then
        pass "assess reports a requested target that differs from the pinned one"
    else
        fail "assess reports a requested target that differs from the pinned one" "got: $moved"
    fi
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$R_ID" 2>&1) || true
    check_yaml "$output" "status: done" "the replacement's accepted attempt closes at the pinned target"

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M4: acceptance binds to the exact submission (independent review finding 1)"
    output=$("$MANNA" create "Managed resubmit" "A accepted, B must not inherit it" 2>&1) || true
    B_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file resubmit item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$B_ID" --reason "lead for resubmit" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$B_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$B_ID" >/dev/null 2>&1
    printf 'Submission A: tested revision A.\n' > sub-a.md
    SUB_A=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$B_ID" --report sub-a.md --json 2>/dev/null | json_field 'd["managed"]["submission"]["id"]')
    if [[ "$SUB_A" == sub-* ]]; then
        pass "a submission carries a stable id"
    else
        fail "a submission carries a stable id" "got: $SUB_A"
    fi
    output=$(lead_accept $B_ID integration HEAD "Reviewed submission A" 2>&1) || true
    check_yaml "$output" "submission: $SUB_A" "the acceptance names the submission it reviewed"
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed correct "$B_ID" --reason "Submission A needs changes" >/dev/null 2>&1
    sent_back_exit=0
    lead_accept $B_ID integration HEAD "again" >/dev/null 2>&1 || sent_back_exit=$?
    check_exit 1 "$sent_back_exit" "a submission that was sent back cannot be accepted until resubmitted"
    printf 'Submission B: changed result, not reviewed.\n' > sub-b.md
    SUB_B=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$B_ID" --report sub-b.md --json 2>/dev/null | json_field 'd["managed"]["submission"]["id"]')
    if [[ "$SUB_B" == sub-* && "$SUB_B" != "$SUB_A" ]]; then
        pass "a resubmission is a new submission"
    else
        fail "a resubmission is a new submission" "A=$SUB_A B=$SUB_B"
    fi
    assess_b=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$B_ID" --json 2>/dev/null)
    if [[ "$(printf '%s' "$assess_b" | json_field 'd["closable"]')" == "False" ]]; then
        pass "after an unreviewed resubmit the item is not closable"
    else
        fail "after an unreviewed resubmit the item is not closable" "$assess_b"
    fi
    if [[ "$(printf '%s' "$assess_b" | json_field 'd["superseded_acceptances"][0]["submission"] + "|" + d["superseded_acceptances"][0]["why"]')" == "$SUB_A|given on an earlier submission; the current one has not been accepted" ]]; then
        pass "assess names the superseded acceptance and why it no longer counts"
    else
        fail "assess names the superseded acceptance and why it no longer counts" "$assess_b"
    fi
    worker_b_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" done "$B_ID" >/dev/null 2>&1 || worker_b_exit=$?
    check_exit 2 "$worker_b_exit" "the worker cannot close B on A's acceptance"
    lead_b_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$B_ID" >/dev/null 2>&1 || lead_b_exit=$?
    check_exit 2 "$lead_b_exit" "the coordinator cannot close B on A's acceptance"
    output=$("$MANNA" show "$B_ID" 2>&1) || true
    check_yaml "$output" "status: in_progress" "B is still in progress"
    lead_accept $B_ID integration HEAD "Reviewed submission B" >/dev/null 2>&1
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$B_ID" 2>&1) || true
    check_yaml "$output" "status: done" "B closes once B itself is accepted"

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M4b: an acceptance names what it reviewed (review pass 2, finding 1)"
    output=$("$MANNA" create "Managed accept race" "accept paused, submission changes" 2>&1) || true
    AR_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file accept-race item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$AR_ID" --reason "lead for accept race" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$AR_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$AR_ID" >/dev/null 2>&1
    printf 'Submission A reviewed\n' > ar-a.md
    AR_SUB_A=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$AR_ID" --report ar-a.md --json 2>/dev/null | json_field 'd["managed"]["submission"]["id"]')
    no_sub_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AR_ID" --check integration --target HEAD --evidence "x" --attempt 1 >/dev/null 2>&1 || no_sub_exit=$?
    check_exit 2 "$no_sub_exit" "accept without --submission is refused by the CLI"
    # The coordinator reviewed A, starts accepting, and holds before the lock;
    # the worker submits B meanwhile. The acceptance must not land on B.
    MANNA_MANAGED_PAUSE_BEFORE_LOCK=3 MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" accept "$AR_ID" --check integration --target HEAD --evidence "I reviewed submission A" --submission "$AR_SUB_A" --attempt 1 > ar-accept.out 2>&1 &
    AR_ACCEPT_PID=$!
    sleep 1.2
    printf 'Submission B NOT reviewed\n' > ar-b.md
    AR_SUB_B=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$AR_ID" --report ar-b.md --json 2>/dev/null | json_field 'd["managed"]["submission"]["id"]')
    ar_exit=0
    wait "$AR_ACCEPT_PID" || ar_exit=$?
    output=$(cat ar-accept.out)
    check_exit 1 "$ar_exit" "an acceptance started on A is refused once B is the current submission"
    check_yaml "$output" "you reviewed submission $AR_SUB_A" "the refusal names the submission the coordinator reviewed"
    ar_state=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$AR_ID" --json 2>/dev/null | json_field 'str(d["closable"]) + "/" + str(len(d["accepted_checks"])) + "/" + str(len(d["record"]["acceptances"]))')
    if [[ "$ar_state" == "False/0/0" ]]; then
        pass "nothing was accepted and B is not closable"
    else
        fail "nothing was accepted and B is not closable" "got: $ar_state"
    fi
    wrong_attempt_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AR_ID" --check integration --target HEAD --evidence "x" --submission "$AR_SUB_B" --attempt 2 >/dev/null 2>&1 || wrong_attempt_exit=$?
    check_exit 1 "$wrong_attempt_exit" "an acceptance naming the wrong attempt is refused"
    stale_sub_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AR_ID" --check integration --target HEAD --evidence "x" --submission "$AR_SUB_A" --attempt 1 >/dev/null 2>&1 || stale_sub_exit=$?
    check_exit 1 "$stale_sub_exit" "an acceptance naming the superseded submission is refused"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AR_ID" --check integration --target HEAD --evidence "I reviewed submission B" --submission "$AR_SUB_B" --attempt 1 2>&1) || true
    check_yaml "$output" "submission: $AR_SUB_B" "an acceptance naming the current submission lands"

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M4c: a blocked assessment never authorizes a close (review pass 2, finding 2)"
    # The board checkout's own branch is the integration target here, as in
    # the reviewer's fixture; it advances after acceptance.
    BA_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    output=$("$MANNA" create "Managed blocked assessment" "target advances after acceptance" 2>&1) || true
    BA_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file blocked-assessment item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$BA_ID" --reason "lead for blocked assessment" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$BA_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$BA_ID" >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$BA_ID" --report half.md >/dev/null 2>&1
    lead_accept $BA_ID integration "$BA_BRANCH" "reviewed at the branch head" >/dev/null 2>&1
    EARLY_TOKEN=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$BA_ID" --json 2>/dev/null | json_field 'd["assessment"]')
    if [[ "$EARLY_TOKEN" == assess:v2:* ]]; then
        pass "a closable assessment yields an assess:v2 token"
    else
        fail "a closable assessment yields an assess:v2 token" "got: $EARLY_TOKEN"
    fi
    # The target branch advances after acceptance.
    printf 'advance\n' > advance.txt
    git add advance.txt
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "the branch advances past the pinned target"
    BLOCKED_TOKEN=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$BA_ID" --target "$BA_BRANCH" --json 2>/dev/null | json_field 'd["assessment"] + "|" + str(d["closable"])')
    if [[ "$BLOCKED_TOKEN" == blocked:v2:*"|False" ]]; then
        pass "assess --target <branch> is blocked and yields a blocked:v2 token"
    else
        fail "assess --target <branch> is blocked and yields a blocked:v2 token" "got: $BLOCKED_TOKEN"
    fi
    BLOCKED_TOKEN="${BLOCKED_TOKEN%%|*}"
    blocked_close_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$BA_ID" --assessment "$BLOCKED_TOKEN" 2>&1) || blocked_close_exit=$?
    check_exit 2 "$blocked_close_exit" "done refuses a blocked assessment token"
    check_yaml "$output" "blocked assessment never authorizes" "the refusal says why"
    early_close_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$BA_ID" --assessment "$EARLY_TOKEN" 2>&1) || early_close_exit=$?
    check_exit 2 "$early_close_exit" "done refuses a closable token taken before the reference moved"
    check_yaml "$output" "points at" "the refusal names where the reference points now"
    v1_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$BA_ID" --assessment "assess:0123456789abcdef" >/dev/null 2>&1 || v1_exit=$?
    check_exit 2 "$v1_exit" "done refuses an old-format assessment token"
    output=$("$MANNA" show "$BA_ID" 2>&1) || true
    check_yaml "$output" "status: in_progress" "the item is still in progress after the refused closes"
    FRESH_TOKEN=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$BA_ID" --json 2>/dev/null | json_field 'd["assessment"]')
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$BA_ID" --assessment "$FRESH_TOKEN" 2>&1) || true
    check_yaml "$output" "status: done" "a fresh closable assessment taken under the current conditions closes"

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M6: an audit that cannot be written stops the item until recovered (review pass 2, finding 3)"
    output=$("$MANNA" create "Managed audit failure" "lifecycle destination unwritable" 2>&1) || true
    AF_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file audit-failure item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$AF_ID" --reason "lead for audit failure" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$AF_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$AF_ID" >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$AF_ID" --report half.md >/dev/null 2>&1
    AF_SUB=$(reviewed_submission "$AF_ID")
    chmod 000 .manna/lifecycle.jsonl
    af_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AF_ID" --check integration --target HEAD --evidence "Audit-failure fixture acceptance" --submission "$AF_SUB" --attempt 1 2>&1) || af_exit=$?
    if [[ "$af_exit" -ne 0 ]]; then
        pass "an acceptance whose audit cannot be written does not succeed"
    else
        fail "an acceptance whose audit cannot be written does not succeed" "$output"
    fi
    check_yaml "$output" "did not complete" "the failure names the incomplete transaction"
    pending=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$AF_ID" --json 2>/dev/null | json_field 'str(len(d["incomplete_transactions"])) + "/" + str(d["closable"]) + "/" + d["next_action"]')
    if [[ "$pending" == "1/False/agent-do manna managed recover $AF_ID" ]]; then
        pass "assess reports the incomplete transaction, blocks closure, and names recover"
    else
        fail "assess reports the incomplete transaction, blocks closure, and names recover" "got: $pending"
    fi
    chmod 644 .manna/lifecycle.jsonl
    second_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$AF_ID" --check integration --target HEAD --evidence "again" --submission "$AF_SUB" --attempt 1 >/dev/null 2>&1 || second_exit=$?
    check_exit 1 "$second_exit" "no further acceptance lands while the transaction is incomplete"
    blocked_submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$AF_ID" --report half.md >/dev/null 2>&1 || blocked_submit_exit=$?
    check_exit 1 "$blocked_submit_exit" "no submission lands while the transaction is incomplete"
    blocked_done_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$AF_ID" >/dev/null 2>&1 || blocked_done_exit=$?
    check_exit 2 "$blocked_done_exit" "no close lands while the transaction is incomplete"
    stranger_recover_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" managed recover "$AF_ID" >/dev/null 2>&1 || stranger_recover_exit=$?
    check_exit 2 "$stranger_recover_exit" "a stranger cannot recover the transaction"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$AF_ID" --json 2>/dev/null | json_field 'str(len(d["recovered"]))')
    if [[ "$output" == "1" ]]; then
        pass "the coordinator recovers the incomplete transaction"
    else
        fail "the coordinator recovers the incomplete transaction" "got: $output"
    fi
    accept_lines=$(grep -c "\"action\":\"accept\",\"issue_id\":\"$AF_ID\"" .manna/lifecycle.jsonl || true)
    check_exit 1 "$accept_lines" "recovery writes the missing audit line exactly once"
    after=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$AF_ID" --json 2>/dev/null | json_field 'str(len(d["incomplete_transactions"])) + "/" + str(d["closable"]) + "/" + str(len(d["accepted_checks"]))')
    if [[ "$after" == "0/True/1" ]]; then
        pass "after recovery the acceptance stands once and the item is closable"
    else
        fail "after recovery the acceptance stands once and the item is closable" "got: $after"
    fi
    if [[ ! -e .manna/managed-intent.json ]]; then
        pass "no intent remains after recovery"
    else
        fail "no intent remains after recovery" "$(cat .manna/managed-intent.json)"
    fi
    # The close audit is a transaction too: an unwritable destination leaves
    # the row done, the audit pending, and the command FAILED (nonzero), so
    # no caller reads a clean close; recover finishes it.
    chmod 000 .manna/lifecycle.jsonl
    close_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" done "$AF_ID" 2>&1) || close_exit=$?
    check_exit 2 "$close_exit" "a close whose audit transaction did not complete exits nonzero (review pass 3, finding 1)"
    check_yaml "$output" "success: false" "the incomplete close is a failure, not a warning"
    check_yaml "$output" "status: done" "the failure still reports the durable row"
    check_yaml "$output" "did not complete" "the failure names the incomplete close transaction"
    check_yaml "$output" "next_action: agent-do manna managed recover $AF_ID" "the failure names recover"
    output=$("$MANNA" show "$AF_ID" 2>&1) || true
    check_yaml "$output" "status: done" "the row is done on the board"
    pending=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$AF_ID" --json 2>/dev/null | json_field 'str(len(d["incomplete_transactions"])) + "/" + d["incomplete_transactions"][0]["action"] + "/" + d["next_action"]')
    if [[ "$pending" == "1/close/agent-do manna managed recover $AF_ID" ]]; then
        pass "assess reports the incomplete close transaction and names recover"
    else
        fail "assess reports the incomplete close transaction and names recover" "got: $pending"
    fi
    chmod 644 .manna/lifecycle.jsonl
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$AF_ID" --json 2>/dev/null | json_field 'str(len(d["recovered"]))')
    check_exit 1 "$output" "recover finishes the close's audit transaction"
    close_lines=$(grep -c "\"action\":\"close\",\"issue_id\":\"$AF_ID\"" .manna/lifecycle.jsonl || true)
    check_exit 1 "$close_lines" "the close audit line lands exactly once"
    if [[ ! -e .manna/managed-intent.json ]]; then
        pass "no intent remains after the close is recovered"
    else
        fail "no intent remains after the close is recovered" "$(cat .manna/managed-intent.json)"
    fi

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M7: a grant or revocation whose writes did not both land stops the board until the operator recovers it (review pass 3, finding 2)"
    output=$("$MANNA" create "Managed board recovery" "grant audit unwritable" 2>&1) || true
    BR_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file board-recovery item"
    # The operator: a terminal, no pinned agent identity.
    op() {
        script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
            -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
            "$@" </dev/null
    }
    output=$(op "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$BR_ID" --reason "lead for board recovery" --json 2>/dev/null)
    # pty output carries a ^D echo before the payload: take the id by shape.
    BR_GRANT1=$(printf '%s\n' "$output" | grep -o 'grant-[0-9a-f]\{12\}' | head -1)
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$BR_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$BR_ID" >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$BR_ID" --report half.md >/dev/null 2>&1
    BR_SUB=$(reviewed_submission "$BR_ID")
    # A second grant whose audit cannot be written (the reviewer's sequence):
    # the grants file takes it, the audit does not, the intent stays pending.
    chmod 000 .manna/lifecycle.jsonl
    grant_exit=0
    output=$(op "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$BR_ID" --reason "board recovery fixture" 2>&1) || grant_exit=$?
    output=$(printf '%s' "$output" | tr -d '\r')
    chmod 644 .manna/lifecycle.jsonl
    check_exit 1 "$grant_exit" "a grant whose audit cannot be written does not succeed"
    check_yaml "$output" "managed recover board" "the failure names board recovery"
    intent_scope=$(python3 -c 'import json; d=json.load(open(".manna/managed-intent.json")); print(",".join(i["issue_id"]+":"+i["action"] for i in d["intents"]))' 2>/dev/null)
    if [[ "$intent_scope" == "board:grant" ]]; then
        pass "the pending intent is board-scoped"
    else
        fail "the pending intent is board-scoped" "got: $intent_scope"
    fi
    grants_for_item=$("$MANNA" coordinator list --json 2>/dev/null | json_field 'str(len([g for g in d["grants"] if g["scope"]["items"] == ["'"$BR_ID"'"]]))')
    check_exit 2 "$grants_for_item" "the grants file took the grant before the audit failed (state landed, audit did not)"
    # Nothing managed moves and no grant changes while the board transaction is pending.
    accept_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$BR_ID" --check integration --target HEAD --evidence "Board recovery fixture" --submission "$BR_SUB" --attempt 1 2>&1) || accept_exit=$?
    check_exit 1 "$accept_exit" "accept refuses while a board transaction is incomplete"
    check_yaml "$output" "recover board" "the acceptance refusal names board recovery"
    submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$BR_ID" --report half.md >/dev/null 2>&1 || submit_exit=$?
    check_exit 1 "$submit_exit" "submit refuses while a board transaction is incomplete"
    require_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$BR_ID" --check extra >/dev/null 2>&1 || require_exit=$?
    check_exit 1 "$require_exit" "managed require refuses while a board transaction is incomplete"
    grant_again_exit=0
    output=$(op "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$BR_ID" --reason "third" 2>&1) || grant_again_exit=$?
    check_exit 1 "$grant_again_exit" "no further grant lands while a board transaction is incomplete"
    check_yaml "$(printf '%s' "$output" | tr -d '\r')" "recover board" "the grant refusal names board recovery"
    revoke_blocked_exit=0
    op "$MANNA" coordinator revoke "$BR_GRANT1" --reason "blocked" >/dev/null 2>&1 || revoke_blocked_exit=$?
    check_exit 1 "$revoke_blocked_exit" "no revocation lands while a board transaction is incomplete"
    pending=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$BR_ID" --json 2>/dev/null | json_field 'str(len(d["incomplete_transactions"])) + "/" + d["incomplete_transactions"][0]["scope"] + "/" + str(d["closable"]) + "/" + d["next_action"]')
    if [[ "$pending" == "1/board/False/operator: agent-do manna managed recover board" ]]; then
        pass "assess reports the board transaction, blocks closure, and names the operator's recovery"
    else
        fail "assess reports the board transaction, blocks closure, and names the operator's recovery" "got: $pending"
    fi
    # Only the operator finishes a board transaction: a coordinator cannot decide its own authority.
    lead_recover_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover board >/dev/null 2>&1 || lead_recover_exit=$?
    check_exit 2 "$lead_recover_exit" "a coordinator cannot recover a board transaction"
    other_recover_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" managed recover board >/dev/null 2>&1 || other_recover_exit=$?
    check_exit 2 "$other_recover_exit" "a stranger cannot recover a board transaction"
    note=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$BR_ID" --json 2>/dev/null | json_field 'd["note"] + "|" + ("board" if d.get("board") else "-")')
    if [[ "$note" == "no incomplete transaction|board" ]]; then
        pass "item recovery reports nothing pending on the item and the board transaction beside it"
    else
        fail "item recovery reports nothing pending on the item and the board transaction beside it" "got: $note"
    fi
    output=$(op "$MANNA" managed recover board --json 2>/dev/null)
    recovered=$(printf '%s\n' "$output" | tr -d '\r' | grep -o '{.*}' | head -1 | json_field 'str(len(d["recovered"]))')
    check_exit 1 "$recovered" "the operator recovers the board transaction"
    grant_lines=$(grep -c "\"action\":\"grant\".*\"reason\":\"board recovery fixture\"" .manna/lifecycle.jsonl || true)
    check_exit 1 "$grant_lines" "recovery writes the grant's audit line exactly once"
    if [[ ! -e .manna/managed-intent.json ]]; then
        pass "no intent remains after board recovery"
    else
        fail "no intent remains after board recovery" "$(cat .manna/managed-intent.json)"
    fi
    accept_after_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" accept "$BR_ID" --check integration --target HEAD --evidence "Board recovery fixture" --submission "$BR_SUB" --attempt 1 >/dev/null 2>&1 || accept_after_exit=$?
    check_exit 0 "$accept_after_exit" "after board recovery the acceptance lands"
    # A revocation that dies after its intent is durable and before the grants
    # file or the audit is written: the file still says the grant is live, and
    # the file is not the truth until the operator recovers the board.
    BR_GRANT2=$("$MANNA" coordinator list --json 2>/dev/null | json_field '[g["id"] for g in d["grants"] if g["reason"] == "board recovery fixture"][0]')
    op "$MANNA" coordinator revoke "$BR_GRANT2" --reason "fixture done" >/dev/null 2>&1
    fault_exit=0
    MANNA_MANAGED_FAULT=after_board_intent op "$MANNA" coordinator revoke "$BR_GRANT1" --reason "rotate" >/dev/null 2>&1 || fault_exit=$?
    check_exit 70 "$fault_exit" "the revocation died after its intent was durable"
    live_in_file=$("$MANNA" coordinator list --json 2>/dev/null | json_field 'str([g for g in d["grants"] if g["id"] == "'"$BR_GRANT1"'"][0].get("revoked") is None)')
    if [[ "$live_in_file" == "True" ]]; then
        pass "the grants file still shows the grant live (its write never ran)"
    else
        fail "the grants file still shows the grant live (its write never ran)" "got: $live_in_file"
    fi
    correct_exit=0
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed correct "$BR_ID" --reason "pending revocation" 2>&1) || correct_exit=$?
    check_exit 1 "$correct_exit" "a coordinator cannot act on a grant whose revocation is pending"
    check_yaml "$output" "recover board" "the refusal names board recovery, not the stale grants file"
    output=$(op "$MANNA" managed recover board --json 2>/dev/null)
    recovered=$(printf '%s\n' "$output" | tr -d '\r' | grep -o '{.*}' | head -1 | json_field 'str(len(d["recovered"]))')
    check_exit 1 "$recovered" "the operator recovers the revocation"
    revoked_now=$("$MANNA" coordinator list --json 2>/dev/null | json_field 'str([g for g in d["grants"] if g["id"] == "'"$BR_GRANT1"'"][0].get("revoked") is not None)')
    if [[ "$revoked_now" == "True" ]]; then
        pass "recovery lands the revocation in the grants file"
    else
        fail "recovery lands the revocation in the grants file" "got: $revoked_now"
    fi
    revoke_lines=$(grep -c "\"action\":\"revoke\".*\"grant\":\"$BR_GRANT1\"" .manna/lifecycle.jsonl || true)
    check_exit 1 "$revoke_lines" "the revocation's audit line lands exactly once"
    after_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed correct "$BR_ID" --reason "after recovery" >/dev/null 2>&1 || after_exit=$?
    check_exit 2 "$after_exit" "after recovery the revocation stands: the coordinator holds no authority"
    unset -f op

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M8: recovery is authorized under the board lock; a grant revoked while recovery waited never carries forward (review pass 3, recovery race)"
    output=$("$MANNA" create "Managed recovery race" "grant revoked before the recovery lock" 2>&1) || true
    RR_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file recovery-race item"
    op() {
        script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
            -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
            "$@" </dev/null
    }
    # pending_txns <id>: the transaction ids pending on an item, comma-joined.
    pending_txns() {
        python3 -c 'import json, os, sys; p = ".manna/managed-intent.json"; d = json.load(open(p)) if os.path.exists(p) else {"intents": []}; print(",".join(i["txn"] for i in d["intents"] if i["issue_id"] == sys.argv[1]))' "$1"
    }
    # state_digest: one digest over the sidecar, the audit, and the intents.
    state_digest() {
        { cat .manna/managed.json .manna/lifecycle.jsonl .manna/managed-intent.json 2>/dev/null || true; } | shasum | awk '{print $1}'
    }
    output=$(op "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$RR_ID" --reason "lead for recovery race" --json 2>/dev/null)
    RR_GRANT=$(printf '%s\n' "$output" | grep -o 'grant-[0-9a-f]\{12\}' | head -1)
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$RR_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$RR_ID" >/dev/null 2>&1
    # The reviewer's fixture: the worker's submission is the transaction left
    # pending (its audit cannot be written), and the coordinator recovers it.
    chmod 000 .manna/lifecycle.jsonl
    rr_submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$RR_ID" --report half.md >/dev/null 2>&1 || rr_submit_exit=$?
    chmod 644 .manna/lifecycle.jsonl
    if [[ "$rr_submit_exit" -ne 0 ]]; then
        pass "the submission whose audit cannot be written does not succeed"
    else
        fail "the submission whose audit cannot be written does not succeed" "exit 0"
    fi
    RR_TXN=$(pending_txns "$RR_ID")
    if [[ "$RR_TXN" == txn-* ]]; then
        pass "the submission's transaction is pending"
    else
        fail "the submission's transaction is pending" "got: $RR_TXN"
    fi
    before_state=$(state_digest)
    # Deterministic race, synchronized on the grant read itself (the reviewer's
    # fixture): the grants file is a FIFO, so the fixture knows the moment
    # recovery reads it, whatever recovery did first. A recovery that reads
    # before its lock (the pass-3 defect) finds the lock free: the fixture
    # takes it, serves the live grant, puts the revoked grant on disk under the
    # lock, and lets go; that recovery would then recover on obsolete
    # permission. A recovery that reads under its lock leaves the fixture
    # refused the lock, and is served the revoked grant: the grants as they
    # are at lock time. Either way the revocation precedes the recovery's
    # lock, and nothing here depends on scheduling.
    mv .manna/coordinators.json rr-grants.real
    mkfifo .manna/coordinators.json
    python3 - "$PWD/.manna/board.lock" "$PWD/.manna/coordinators.json" "$PWD/rr-grants.real" "$RR_GRANT" > rr-fixture.out <<'PY' &
import fcntl, json, os, sys
lock_path, fifo, real, grant_id = sys.argv[1:5]
live = json.load(open(real))
revoked = json.loads(json.dumps(live))
for grant in revoked["grants"]:
    if grant["id"] == grant_id:
        grant["revoked"] = {"at": "2026-10-31T00:30:00Z", "by": "operator-fixture", "reason": "revoked after read, before recovery lock"}
fd = os.open(fifo, os.O_WRONLY)  # returns the moment recovery opens the grants
lock = open(lock_path, "a+")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    held = True
except BlockingIOError:
    held = False
os.write(fd, json.dumps(live if held else revoked).encode())
os.close(fd)
os.unlink(fifo)
with open(real, "w") as handle:
    json.dump(revoked, handle)
os.rename(real, fifo)
if held:
    fcntl.flock(lock, fcntl.LOCK_UN)
print("read-before-lock" if held else "read-under-lock")
PY
    RR_FIXTURE_PID=$!
    rr_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$RR_ID" > rr-recover.out 2>&1 || rr_exit=$?
    if kill -0 "$RR_FIXTURE_PID" 2>/dev/null; then
        # Recovery ended without ever reading the grants: free the fixture
        # and put the grants file back so the rest of the suite can go on.
        sleep 0.2
        if kill -0 "$RR_FIXTURE_PID" 2>/dev/null; then
            kill "$RR_FIXTURE_PID" 2>/dev/null || true
            rm -f .manna/coordinators.json
            mv rr-grants.real .manna/coordinators.json
            fail "recovery read the grants" "recovery exited $rr_exit without reading the grants file: $(cat rr-recover.out)"
        fi
    fi
    wait "$RR_FIXTURE_PID" 2>/dev/null || true
    output=$(cat rr-recover.out)
    sync_mode=$(cat rr-fixture.out)
    if [[ "$sync_mode" == "read-under-lock" ]]; then
        pass "recovery read the grants under its own lock, not before it"
    else
        fail "recovery read the grants under its own lock, not before it" "the fixture reports: $sync_mode (the grants were read with the lock free, then revoked under the lock)"
    fi
    check_exit 2 "$rr_exit" "a grant revoked before recovery holds the lock does not recover (review pass 3, recovery race)"
    check_yaml "$output" "level under the lock: none" "the refusal reports the authority as it stands under the lock"
    after_state=$(state_digest)
    if [[ "$after_state" == "$before_state" ]]; then
        pass "the refused recovery changed no state and no audit"
    else
        fail "the refused recovery changed no state and no audit" "sidecar/audit/intent digest moved: $before_state -> $after_state"
    fi
    if [[ "$(pending_txns "$RR_ID")" == "$RR_TXN" ]]; then
        pass "the transaction is still pending after the refusal"
    else
        fail "the transaction is still pending after the refusal" "got: $(pending_txns "$RR_ID")"
    fi
    submit_lines=$(grep -c "\"action\":\"submit\",\"issue_id\":\"$RR_ID\"" .manna/lifecycle.jsonl || true)
    check_exit 0 "$submit_lines" "no audit line was written by the refused recovery"
    again_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$RR_ID" >/dev/null 2>&1 || again_exit=$?
    check_exit 2 "$again_exit" "the revoked coordinator stays refused once the lock is free"
    # Preserved: the operator finishes it.
    output=$(op "$MANNA" managed recover "$RR_ID" --json 2>/dev/null)
    recovered=$(printf '%s\n' "$output" | tr -d '\r' | grep -o '{.*}' | head -1 | json_field 'str(len(d["recovered"])) + "/" + (d["recovered"] or ["-"])[0] + "/" + d.get("authority", {}).get("level", "-")')
    if [[ "$recovered" == "1/$RR_TXN/operator" ]]; then
        pass "the operator recovers the transaction the revoked coordinator could not"
    else
        fail "the operator recovers the transaction the revoked coordinator could not" "got: $recovered"
    fi
    submit_lines=$(grep -c "\"action\":\"submit\",\"issue_id\":\"$RR_ID\"" .manna/lifecycle.jsonl || true)
    check_exit 1 "$submit_lines" "the submission's audit line lands exactly once"
    if [[ -z "$(pending_txns "$RR_ID")" ]]; then
        pass "no intent remains after the operator's recovery"
    else
        fail "no intent remains after the operator's recovery" "$(cat .manna/managed-intent.json)"
    fi
    # Preserved: the session that started a transaction finishes it, grant or
    # no grant. The worker's next submission is left pending the same way.
    chmod 000 .manna/lifecycle.jsonl
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$RR_ID" --report half.md >/dev/null 2>&1 || true
    chmod 644 .manna/lifecycle.jsonl
    RR_TXN2=$(pending_txns "$RR_ID")
    stranger_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" managed recover "$RR_ID" >/dev/null 2>&1 || stranger_exit=$?
    check_exit 2 "$stranger_exit" "a stranger cannot recover the worker's transaction"
    recovered=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" managed recover "$RR_ID" --json 2>/dev/null | json_field 'str(len(d["recovered"])) + "/" + (d["recovered"] or ["-"])[0] + "/" + d.get("authority", {}).get("level", "-")')
    if [[ "$recovered" == "1/$RR_TXN2/owner" ]]; then
        pass "the session that started the transaction recovers it without a grant"
    else
        fail "the session that started the transaction recovers it without a grant" "got: $recovered"
    fi
    # The board's own pending transaction is read under the lock too: a
    # coordinator recovery that holds before the lock, while a revocation of
    # its grant dies with its intent durable, finds the board pending when it
    # holds the lock and is refused naming board recovery (the grants file
    # still shows the grant live; the file is not the truth).
    output=$(op "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$RR_ID" --reason "lead again for the board race" --json 2>/dev/null)
    RR_GRANT_B=$(printf '%s\n' "$output" | grep -o 'grant-[0-9a-f]\{12\}' | head -1)
    chmod 000 .manna/lifecycle.jsonl
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$RR_ID" --report half.md >/dev/null 2>&1 || true
    chmod 644 .manna/lifecycle.jsonl
    RR_TXN3=$(pending_txns "$RR_ID")
    item_audit_before=$(grep -c "\"issue_id\":\"$RR_ID\"" .manna/lifecycle.jsonl || true)
    MANNA_MANAGED_PAUSE_BEFORE_LOCK=3 MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" managed recover "$RR_ID" > rr-board-recover.out 2>&1 &
    RR_BOARD_PID=$!
    sleep 1.2
    board_fault_exit=0
    MANNA_MANAGED_FAULT=after_board_intent op "$MANNA" coordinator revoke "$RR_GRANT_B" --reason "rotate during recovery" >/dev/null 2>&1 || board_fault_exit=$?
    check_exit 70 "$board_fault_exit" "the revocation died after its intent was durable, while recovery waited"
    rr_board_exit=0
    wait "$RR_BOARD_PID" || rr_board_exit=$?
    output=$(cat rr-board-recover.out)
    check_exit 2 "$rr_board_exit" "a coordinator recovery that finds the board pending under the lock is refused"
    check_yaml "$output" "recover board" "the refusal names board recovery, not the stale grants file"
    if [[ "$(pending_txns "$RR_ID")" == "$RR_TXN3" ]]; then
        pass "the item's transaction is still pending after the board refusal"
    else
        fail "the item's transaction is still pending after the board refusal" "got: $(pending_txns "$RR_ID")"
    fi
    item_audit_after=$(grep -c "\"issue_id\":\"$RR_ID\"" .manna/lifecycle.jsonl || true)
    check_exit "$item_audit_before" "$item_audit_after" "the refused recovery wrote no audit line for the item"
    output=$(op "$MANNA" managed recover board --json 2>/dev/null)
    recovered=$(printf '%s\n' "$output" | tr -d '\r' | grep -o '{.*}' | head -1 | json_field 'str(len(d["recovered"]))')
    check_exit 1 "$recovered" "the operator finishes the revocation"
    lead_after_exit=0
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed recover "$RR_ID" >/dev/null 2>&1 || lead_after_exit=$?
    check_exit 2 "$lead_after_exit" "once the revocation lands the coordinator holds nothing and stays refused"
    recovered=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" managed recover "$RR_ID" --json 2>/dev/null | json_field 'str(len(d["recovered"])) + "/" + (d["recovered"] or ["-"])[0]')
    if [[ "$recovered" == "1/$RR_TXN3" ]]; then
        pass "the session that started the transaction finishes it after the board recovered"
    else
        fail "the session that started the transaction finishes it after the board recovered" "got: $recovered"
    fi
    unset -f op pending_txns state_digest

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M5: atomic transitions, authority under the lock, interrupted writes, races"
    # (a) An interrupted release: the process dies after the pending phase.
    output=$("$MANNA" create "Managed interrupted" "release dies mid-way" 2>&1) || true
    I_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file interrupted item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$I_ID" --reason "lead for interrupted" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$I_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$I_ID" >/dev/null 2>&1
    fault_exit=0
    MANNA_MANAGED_FAULT=after_release_pending MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" managed release "$I_ID" --reason "worker unreachable" --isolated-checkout "$REPLACEMENT_TREE" >/dev/null 2>&1 || fault_exit=$?
    check_exit 70 "$fault_exit" "the injected fault ends the process after the pending phase"
    output=$("$MANNA" show "$I_ID" 2>&1) || true
    check_yaml "$output" "claimed_by: $WORKER_ID" "the row still carries the claim after the interrupted release"
    interrupted=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$I_ID" --json 2>/dev/null | json_field 'str(d["release_interrupted"]) + "/" + str(d["attempt"]) + "/" + d["next_action"]')
    if [[ "$interrupted" == "True/2/coordinator: agent-do manna managed release $I_ID --reason \"complete the interrupted release\"" ]]; then
        pass "assess reports the interrupted release and the exact next action"
    else
        fail "assess reports the interrupted release and the exact next action" "got: $interrupted"
    fi
    blocked_submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$I_ID" --report half.md >/dev/null 2>&1 || blocked_submit_exit=$?
    check_exit 1 "$blocked_submit_exit" "no submission lands on an interrupted release"
    stranger_resume_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" managed release "$I_ID" --reason "finish it" >/dev/null 2>&1 || stranger_resume_exit=$?
    check_exit 2 "$stranger_resume_exit" "a stranger cannot complete the interrupted release"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$I_ID" --reason "complete the interrupted release" 2>&1) || true
    check_yaml "$output" "status: open" "the coordinator completes the interrupted release"
    check_yaml "$output" "attempt: 2" "resuming does not advance the attempt a second time"
    check_yaml "$output" "claim_release: released" "the pending marker is cleared"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed history "$I_ID" --json 2>/dev/null | json_field '",".join(e["action"] for e in d["events"])')
    if [[ "$output" == "require,claim,release,release_resume" ]]; then
        pass "the audit holds the interrupted release and its completion"
    else
        fail "the audit holds the interrupted release and its completion" "got: $output"
    fi

    # (b) Revocation race: the grant is revoked by a writer that wins the board
    # lock while the coordinator's accept is already past its preview.
    output=$("$MANNA" create "Managed revoked" "grant revoked under the lock" 2>&1) || true
    V_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file revoked item"
    output=$(script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$V_ID" --reason "lead for revoked" 2>&1 </dev/null | tr -d '\r') || true
    V_GRANT=$(printf '%s\n' "$output" | grep -o 'grant-[0-9a-f]\{12\}' | head -1)
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$V_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$V_ID" >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$V_ID" --report half.md >/dev/null 2>&1
    # The accept passes its preview (grant live) and then holds before the
    # lock; meanwhile a writer takes the lock, revokes the grant, and lets go.
    # The recheck under the lock must refuse the accept.
    V_SUB=$(reviewed_submission "$V_ID")
    MANNA_MANAGED_PAUSE_BEFORE_LOCK=3 MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" \
        "$MANNA" accept "$V_ID" --check integration --target HEAD --evidence "raced" --submission "$V_SUB" --attempt 1 > race-accept.out 2>&1 &
    ACCEPT_PID=$!
    sleep 1.2
    python3 - "$PWD/.manna/board.lock" "$PWD/.manna/coordinators.json" "$V_GRANT" <<'PY'
import fcntl, json, sys
lock = open(sys.argv[1], "a+")
fcntl.flock(lock, fcntl.LOCK_EX)
grants = json.load(open(sys.argv[2]))
for grant in grants["grants"]:
    if grant["id"] == sys.argv[3]:
        grant["revoked"] = {"at": "2026-10-30T00:00:00Z", "by": "operator-race", "reason": "revoked while the accept waited"}
json.dump(grants, open(sys.argv[2], "w"))
fcntl.flock(lock, fcntl.LOCK_UN)
PY
    race_exit=0
    wait "$ACCEPT_PID" || race_exit=$?
    output=$(cat race-accept.out)
    check_exit 1 "$race_exit" "an accept that passed its preview is refused once the grant is revoked under the lock"
    check_yaml "$output" "no longer holds coordinator authority" "the refusal names the lost authority"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$V_ID" --json 2>/dev/null | json_field 'str(len(d["accepted_checks"])) + "/" + d["authority"]["level"]')
    if [[ "$output" == "0/none" ]]; then
        pass "nothing was accepted and the session no longer coordinates"
    else
        fail "nothing was accepted and the session no longer coordinates" "got: $output"
    fi

    # (c) Concurrent release and claim: whichever wins, the board is coherent.
    for round in 1 2 3; do
        output=$("$MANNA" create "Managed race $round" "release vs claim" 2>&1) || true
        C_ID=$(extract_id "$output")
        git add -A >/dev/null 2>&1
        git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file race $round"
        script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
            -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
            "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$C_ID" --reason "lead for race" >/dev/null 2>&1 </dev/null
        MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$C_ID" --check integration >/dev/null 2>&1
        MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$C_ID" >/dev/null 2>&1
        MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed release "$C_ID" --reason "race" --isolated-checkout "$REPLACEMENT_TREE" >/dev/null 2>&1 &
        RELEASE_PID=$!
        claim_exit=0
        MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" claim "$C_ID" >/dev/null 2>&1 || claim_exit=$?
        wait "$RELEASE_PID" 2>/dev/null || true
        state=$("$MANNA" show "$C_ID" 2>&1 | grep -E "^  (claimed_by|status):" | sed 's/^  //' | paste -sd' ' -)
        attempt=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$C_ID" --json 2>/dev/null | json_field 'str(d["attempt"]) + "/" + str(d["release_interrupted"])')
        case "$claim_exit|$state" in
            "0|status: in_progress claimed_by: $OTHER_ID"|"0|claimed_by: $OTHER_ID status: in_progress")
                claim_won="after"
                ;;
            *"|status: open"|*"|status: open "*)
                claim_won="lost"
                ;;
            *)
                claim_won="incoherent"
                ;;
        esac
        if [[ "$claim_won" != "incoherent" && "$attempt" == "2/False" ]]; then
            pass "race $round: one coherent outcome (claim exit $claim_exit, $state, attempt 2, no interrupted release)"
        else
            fail "race $round: board incoherent" "claim exit $claim_exit, state '$state', $attempt"
        fi
    done

    # (d) Abandon by the worker: attempt ends and the claim releases in one transaction.
    output=$("$MANNA" create "Managed abandon" "worker walks away" 2>&1) || true
    A_ID=$(extract_id "$output")
    git add -A >/dev/null 2>&1
    git -c user.email=manna@test -c user.name=manna-test commit -q -m "board: file abandon item"
    script -q /dev/null env -u MANNA_SESSION_ID -u MANNA_SESSION_TOKEN \
        -u CODEX_THREAD_ID -u CLAUDE_THREAD_ID -u CLAUDE_SESSION_ID -u CLAUDE_AGENT_ID \
        "$MANNA" coordinator grant --session "$LEAD_ID" --proof "$LEAD_PROOF" --item "$A_ID" --reason "lead for abandon" >/dev/null 2>&1 </dev/null
    MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" managed require "$A_ID" --check integration >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$A_ID" >/dev/null 2>&1
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$A_ID" --report half.md >/dev/null 2>&1
    stranger_abandon_exit=0
    MANNA_SESSION_ID="$OTHER_ID" MANNA_SESSION_TOKEN="$OTHER_TOKEN" "$MANNA" abandon "$A_ID" >/dev/null 2>&1 || stranger_abandon_exit=$?
    check_exit 1 "$stranger_abandon_exit" "a stranger cannot abandon the worker's managed claim"
    output=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" abandon "$A_ID" 2>&1) || true
    check_yaml "$output" "status: open" "the worker abandons its managed claim"
    output=$(MANNA_SESSION_ID="$LEAD_ID" MANNA_SESSION_TOKEN="$LEAD_TOKEN" "$MANNA" assess "$A_ID" --json 2>/dev/null | json_field 'str(d["attempt"]) + "/" + str(d["release_interrupted"]) + "/" + d["record"]["releases"][-1]["basis"] + "/" + d["record"]["releases"][-1]["claim_release"]')
    if [[ "$output" == "2/False/abandon/released" ]]; then
        pass "abandon ends the attempt and completes its two-phase release"
    else
        fail "abandon ends the attempt and completes its two-phase release" "got: $output"
    fi
    abandoned_submit_exit=0
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" submit "$A_ID" --report half.md >/dev/null 2>&1 || abandoned_submit_exit=$?
    check_exit 1 "$abandoned_submit_exit" "the worker that abandoned cannot submit"

    # ------------------------------------------------------------------------
    echo ""
    echo "Test M3: unmanaged items keep every documented path"
    output=$("$MANNA" create "Plain work" 2>&1) || true
    P_ID=$(extract_id "$output")
    MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" claim "$P_ID" >/dev/null 2>&1
    output=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" done "$P_ID" 2>&1) || true
    check_yaml "$output" "authority: owner" "an unmanaged owner close still works"
    unmanaged=$(MANNA_SESSION_ID="$WORKER_ID" MANNA_SESSION_TOKEN="$WORKER_TOKEN" "$MANNA" assess "$P_ID" --json 2>/dev/null | json_field 'd["managed"]')
    if [[ "$unmanaged" == "False" ]]; then
        pass "assess answers for unmanaged items too"
    else
        fail "assess answers for unmanaged items too" "got: $unmanaged"
    fi
    output=$("$MANNA" managed doctor 2>&1) || true
    check_yaml "$output" "managed_lifecycle" "doctor names the capability this binary carries"
    check_yaml "$output" "live:" "doctor reports whether the lifecycle is live, not only compiled"

    cd "$TEST_DIR"
    rm -rf "$MANAGED_DIR"
else
    echo "  - skipped: needs macOS script(1) to lend the operator a pseudo-terminal"
fi

# ============================================================================
# Portable Federation Tests
# ============================================================================

echo ""
echo "=== Portable Federation Tests ==="

FED_SOURCE=$(mktemp -d)
FED_TARGET=$(mktemp -d)
FED_REPLICA=$(mktemp -d)
FED_CLONE=$(mktemp -d)
SERVE_DIR="$SCRIPT_DIR/../serve"

register_federation_roots() {
    local serve_python="python3"
    if ! "$serve_python" -c 'import yaml' >/dev/null 2>&1 \
        && [[ -x /usr/bin/python3 ]] \
        && /usr/bin/python3 -c 'import yaml' >/dev/null 2>&1; then
        serve_python="/usr/bin/python3"
    fi
    PYTHONPATH="$SERVE_DIR" "$serve_python" - "$@" <<'PY'
import sys
from pathlib import Path

from serve import register_board

for value in sys.argv[1:]:
    register_board(Path(value))
PY
}

clear_federation_registry() {
    rm -f "$AGENT_DO_HOME/manna/serve/boards.json"
}

cd "$FED_SOURCE"
git init -q
git config user.name "Manna Federation Fixture"
git config user.email "manna-federation@example.invalid"
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "federation_created: true" "new source board auto-enrolls in federation"
FED_SOURCE_BOARD=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
output=$("$MANNA" create "Federated source" 2>&1) || true
FED_SOURCE_ID=$(extract_id "$output")
"$MANNA" sync >/dev/null 2>&1
output=$("$MANNA" federation status 2>&1) || true
check_yaml "$output" "enabled: true" "new board reports federation identity immediately"
check_yaml "$output" "board_id: $FED_SOURCE_BOARD" "federation status reports the init identity"
output=$("$MANNA" federation init 2>&1) || true
check_yaml "$output" "success: true" "explicit federation init remains available"
check_yaml "$output" "changed: false" "explicit federation init is an idempotent repair command"
[[ "$FED_SOURCE_BOARD" =~ ^mb-[a-f0-9]{32}$ ]] \
    && pass "automatic enrollment emits a 128-bit board identity" \
    || fail "automatic enrollment emits a 128-bit board identity" "$FED_SOURCE_BOARD"
git add -- .manna .handoff
git commit -qm "test: source federation fixture"

cd "$FED_TARGET"
git init -q
git config user.name "Manna Federation Fixture"
git config user.email "manna-federation@example.invalid"
output=$("$MANNA" init 2>&1) || true
FED_TARGET_BOARD=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
check_yaml "$output" "federation_created: true" "new target board auto-enrolls in federation"
output=$("$MANNA" create "Federated target" 2>&1) || true
FED_TARGET_ID=$(extract_id "$output")
output=$("$MANNA" federation init 2>&1) || true
check_yaml "$output" "changed: false" "target federation repair preserves automatic identity"
git add -- .manna .handoff
git commit -qm "test: target federation fixture"

cd "$FED_SOURCE"
FED_SOURCE_HANDOFF=$(find .handoff -type f -name "*$FED_SOURCE_ID*" -print -quit)
FED_ISSUES_BEFORE=$(git hash-object .manna/issues.jsonl)
FED_HANDOFF_BEFORE=$(git hash-object "$FED_SOURCE_HANDOFF")
FED_TARGET_URI="manna://$FED_TARGET_BOARD/$FED_TARGET_ID"
output=$("$MANNA" relate "$FED_SOURCE_ID" --kind informed_by --to "$FED_TARGET_URI" --hint target-repo 2>&1) || true
check_yaml "$output" "success: true" "relate writes one typed outbound declaration"
check_yaml "$output" "$FED_TARGET_URI" "relate preserves the board-qualified target URI"
[[ "$FED_ISSUES_BEFORE" == "$(git hash-object .manna/issues.jsonl)" ]] \
    && pass "relate preserves source issue bytes" \
    || fail "relate preserves source issue bytes" "issues.jsonl changed"
[[ "$FED_HANDOFF_BEFORE" == "$(git hash-object "$FED_SOURCE_HANDOFF")" ]] \
    && pass "relate preserves source handoff bytes" \
    || fail "relate preserves source handoff bytes" "handoff changed"
output=$("$MANNA" relations --json 2>&1) || true
check_yaml "$output" '"resolved":false' "relations without --resolve reads durable local state only"
if [[ "$output" != *'"resolution"'* ]]; then
    pass "local relation read carries no derived resolution cache"
else
    fail "local relation read carries no derived resolution cache" "$output"
fi
git add -- .manna/federation.yaml
git commit -qm "test: declare federation relation"

clear_federation_registry
unavailable_exit=0
output=$("$MANNA" relations --resolve --check --json 2>&1) || unavailable_exit=$?
check_exit 0 "$unavailable_exit" "unavailable target is a successful degraded check"
check_yaml "$output" '"state":"unavailable"' "unregistered target resolves unavailable"

register_federation_roots "$FED_SOURCE" "$FED_TARGET"
output=$("$MANNA" relations --resolve --check --json 2>&1) || true
check_yaml "$output" '"state":"resolved"' "two registered repositories resolve the relation"
check_yaml "$output" '"status":"open"' "resolver reports the target's open status"

cd "$FED_TARGET"
"$MANNA" claim "$FED_TARGET_ID" >/dev/null 2>&1
"$MANNA" done "$FED_TARGET_ID" >/dev/null 2>&1
git add -- .manna .handoff
git commit -qm "test: complete remote target" -m "Manna: $FED_SOURCE_ID"

cd "$FED_SOURCE"
output=$("$MANNA" relations --resolve --check --json 2>&1) || true
check_yaml "$output" '"status":"done"' "resolver reflects remote completion"
[[ "$FED_ISSUES_BEFORE" == "$(git hash-object .manna/issues.jsonl)" ]] \
    && pass "remote completion preserves source lifecycle bytes" \
    || fail "remote completion preserves source lifecycle bytes" "source issues.jsonl changed"
[[ "$FED_HANDOFF_BEFORE" == "$(git hash-object "$FED_SOURCE_HANDOFF")" ]] \
    && pass "remote completion preserves source handoff bytes" \
    || fail "remote completion preserves source handoff bytes" "source handoff changed"
reconcile_exit=0
output=$("$MANNA" reconcile --json 2>&1) || reconcile_exit=$?
check_exit 0 "$reconcile_exit" "remote Manna trailer cannot create local landed-open evidence"
if [[ "$output" != *"landed_open"* ]]; then
    pass "reconcile ignores target-repository commit trailers"
else
    fail "reconcile ignores target-repository commit trailers" "$output"
fi

cp "$FED_TARGET/.manna/issues.jsonl" "$TEST_DIR/federation-target-issues.jsonl"
: > "$FED_TARGET/.manna/issues.jsonl"
missing_exit=0
output=$("$MANNA" relations --resolve --check --json 2>&1) || missing_exit=$?
check_exit 1 "$missing_exit" "present board with a missing target fails --check"
check_yaml "$output" '"state":"missing"' "present board without target resolves missing"
lint_exit=0
output=$("$MANNA" lint --json 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "remote missing state does not invalidate local lint"
cp "$TEST_DIR/federation-target-issues.jsonl" "$FED_TARGET/.manna/issues.jsonl"

cp -R "$FED_TARGET/." "$FED_REPLICA/"
python3 - "$FED_REPLICA/.manna/issues.jsonl" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
path.write_text("\n".join(line + " " for line in lines) + "\n")
PY
clear_federation_registry
register_federation_roots "$FED_SOURCE" "$FED_TARGET" "$FED_REPLICA"
ambiguous_exit=0
output=$("$MANNA" relations --resolve --check --json 2>&1) || ambiguous_exit=$?
check_exit 1 "$ambiguous_exit" "divergent target replicas fail --check"
check_yaml "$output" '"state":"ambiguous"' "divergent target replicas resolve ambiguous"
clear_federation_registry
register_federation_roots "$FED_REPLICA" "$FED_TARGET" "$FED_SOURCE"
reverse_exit=0
output=$("$MANNA" relations --resolve --check --json 2>&1) || reverse_exit=$?
check_exit 1 "$reverse_exit" "ambiguous resolution is registration-order independent"
check_yaml "$output" '"state":"ambiguous"' "no divergent replica wins by registration order"

clear_federation_registry
git clone -q "$FED_SOURCE" "$FED_CLONE/source-only"
cd "$FED_CLONE/source-only"
clone_lint_exit=0
"$MANNA" lint --json >/dev/null 2>&1 || clone_lint_exit=$?
check_exit 0 "$clone_lint_exit" "source-only clone passes local lint"
clone_reconcile_exit=0
"$MANNA" reconcile --json >/dev/null 2>&1 || clone_reconcile_exit=$?
check_exit 0 "$clone_reconcile_exit" "source-only clone passes local reconcile"
clone_relations_exit=0
output=$("$MANNA" relations --resolve --check --json 2>&1) || clone_relations_exit=$?
check_exit 0 "$clone_relations_exit" "source-only clone retains a valid degraded relation"
check_yaml "$output" '"state":"unavailable"' "source-only clone prints unavailable"

cd "$FED_SOURCE"
output=$("$MANNA" federation fork --reason "intentional fixture fork" 2>&1) || true
check_yaml "$output" "success: true" "federation fork succeeds explicitly"
check_yaml "$output" "relations: []" "federation fork clears inherited relations"
FED_FORK_BOARD=$(echo "$output" | awk '/board_id:/ {print $2; exit}')
if [[ "$FED_FORK_BOARD" =~ ^mb-[a-f0-9]{32}$ && "$FED_FORK_BOARD" != "$FED_SOURCE_BOARD" ]]; then
    pass "federation fork generates a distinct board identity"
else
    fail "federation fork generates a distinct board identity" "$FED_SOURCE_BOARD -> $FED_FORK_BOARD"
fi
FED_ARCHIVE=$(find .manna/federation-archive -type f -name "*.yaml" -print -quit)
[[ -n "$FED_ARCHIVE" && -f "$FED_ARCHIVE" ]] \
    && pass "federation fork archives the inherited manifest" \
    || fail "federation fork archives the inherited manifest" "archive missing"
check_yaml "$(cat "$FED_ARCHIVE")" "$FED_SOURCE_BOARD" "federation archive retains the inherited identity"
check_yaml "$(cat "$FED_ARCHIVE")" "$FED_TARGET_URI" "federation archive retains inherited relations"
git add -- .manna/federation.yaml .manna/federation-archive
fork_lint_exit=0
"$MANNA" lint --json >/dev/null 2>&1 || fork_lint_exit=$?
check_exit 0 "$fork_lint_exit" "tracked fork manifest and archive pass lint"

cd "$TEST_DIR"
rm -rf "$FED_SOURCE" "$FED_TARGET" "$FED_REPLICA" "$FED_CLONE"

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "============================================"
echo "Test Summary: $PASSED passed, $FAILED failed"
echo "============================================"

if [[ "$FAILED" -gt 0 ]]; then
    echo ""
    echo "FAILED: Some tests did not pass"
    exit 1
else
    echo ""
    echo "All tests passed!"
    exit 0
fi
