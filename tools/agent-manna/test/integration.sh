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
