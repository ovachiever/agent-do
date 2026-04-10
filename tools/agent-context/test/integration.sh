#!/usr/bin/env bash
# Integration tests for agent-context
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$SCRIPT_DIR/../agent-context"
PASS=0
FAIL=0

# Use isolated test home
export AGENT_DO_HOME=$(mktemp -d)
trap "rm -rf $AGENT_DO_HOME" EXIT

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    local desc="$1" expected="$2"
    shift 2
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | grep -q "$expected"; then
        echo "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc (expected: $expected)"
        echo "    got: $(echo "$output" | head -3)"
        FAIL=$((FAIL + 1))
    fi
}

echo "agent-context integration tests"
echo "================================"
echo ""

echo "1. Initialization"
check "help works" "$TOOL" --help
check "init creates store" "$TOOL" init
check "init is idempotent" "$TOOL" init
check_output "status shows 0 packages" "0 indexed" "$TOOL" status

echo ""
echo "2. Fetch"
check "fetch URL" "$TOOL" fetch https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md
check_output "list shows 1 package" "1 package" "$TOOL" list

echo ""
echo "3. Fetch LLMs"
check "fetch-llms" "$TOOL" fetch-llms supabase.com
check_output "list shows 2" "2 package" "$TOOL" list

echo ""
echo "4. Search"
check_output "search finds supabase" "supabase" "$TOOL" search supabase
check_output "search --json returns JSON" "success" "$TOOL" search supabase --json

echo ""
echo "5. Get"
check "get by id" "$TOOL" get supabase-com-llms
check_output "get --json has content" "content" "$TOOL" get supabase-com-llms --json
check_output "get unknown shows error" "not found" "$TOOL" get nonexistent-package

echo ""
echo "6. Annotations"
check "annotate" "$TOOL" annotate supabase-com-llms "test note"
check_output "annotate shows on get" "test note" "$TOOL" get supabase-com-llms
check_output "annotate list" "test note" "$TOOL" annotate --list
check "annotate clear" "$TOOL" annotate supabase-com-llms --clear

echo ""
echo "7. Feedback"
check "feedback up" "$TOOL" feedback supabase-com-llms up "good docs"
check "feedback down" "$TOOL" feedback supabase-com-llms down

echo ""
echo "8. Cache"
check_output "cache list" "package" "$TOOL" cache list
check_output "cache stats" "Packages" "$TOOL" cache stats
check "cache pin" "$TOOL" cache pin supabase-com-llms
check "cache clear specific" "$TOOL" cache clear supabase-com-llms
check "cache clear all" "$TOOL" cache clear

echo ""
echo "9. Sources"
check_output "sources empty" "No sources" "$TOOL" sources
check "add-source" "$TOOL" add-source test-source https://example.com/docs
check_output "config keeps trust policy" "trust_policy" grep -n "trust_policy" "$AGENT_DO_HOME/context/config.yaml"
check_output "sources shows entry" "test-source" "$TOOL" sources
check "remove-source" "$TOOL" remove-source test-source
check_output "sources empty after remove" "No sources" "$TOOL" sources

echo ""
echo "10. Scan local"
check "scan-local" "$TOOL" scan-local "$SCRIPT_DIR/../../.."

echo ""
echo "11. Budget"
# Re-fetch something for budget to work with
"$TOOL" fetch https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md >/dev/null 2>&1
check_output "budget" "Budget" "$TOOL" budget 5000 "api documentation"

echo ""
echo "12. Status (final)"
check "status --json" "$TOOL" status --json

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && echo "All tests passed!" || exit 1
