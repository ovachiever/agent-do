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

# Ensure manna binary exists
if [[ ! -x "$MANNA" ]]; then
    echo "ERROR: manna binary not found at $MANNA"
    echo "Run: cd $SCRIPT_DIR/.. && cargo build --release"
    exit 2
fi

# Check if binary is built
if [[ ! -f "$SCRIPT_DIR/../target/release/manna-core" ]]; then
    echo "ERROR: manna-core binary not built"
    echo "Run: cd $SCRIPT_DIR/.. && cargo build --release"
    exit 2
fi

cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

# Set unique session ID for tests
export MANNA_SESSION_ID="ses_test_$$"

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
[[ -d .manna ]] && pass ".manna directory created" || fail ".manna directory created" "Directory not found"
[[ -f .manna/issues.jsonl ]] && pass "issues.jsonl created" || fail "issues.jsonl created" "File not found"

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
cd "$TEST_DIR"
rm -rf .manna
"$MANNA" init >/dev/null 2>&1

# Spawn 10 parallel creates (suppress output)
for i in {1..10}; do
    "$MANNA" create "Concurrent issue $i" >/dev/null 2>&1 &
done
wait

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
