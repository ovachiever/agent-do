#!/usr/bin/env bash
# Test script for agent-do

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DO="$SCRIPT_DIR/agent-do"

echo "Testing agent-do..."
echo

# Test 1: Help
echo "Test 1: --help"
$AGENT_DO --help > /dev/null && echo "  ✓ Help works" || echo "  ✗ Help failed"

# Test 2: Status
echo "Test 2: --status"
$AGENT_DO --status > /dev/null && echo "  ✓ Status works" || echo "  ✗ Status failed"

# Test 3: Offline pattern matching
echo "Test 3: --offline (pattern matching)"
result=$($AGENT_DO --offline "screenshot the iOS simulator" 2>&1)
if echo "$result" | grep -q "agent-ios screenshot"; then
    echo "  ✓ Offline iOS screenshot works"
else
    echo "  ✗ Offline iOS screenshot failed"
    echo "    Got: $result"
fi

# Test 4: Offline network scan
echo "Test 4: --offline (network scan)"
result=$($AGENT_DO --offline "what's using port 3000" 2>&1)
if echo "$result" | grep -q "agent-network"; then
    echo "  ✓ Offline network scan works"
else
    echo "  ✗ Offline network scan failed"
    echo "    Got: $result"
fi

# Test 5: Dry run (requires API key)
echo "Test 5: --dry-run (requires ANTHROPIC_API_KEY)"
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    result=$($AGENT_DO --dry-run "take a screenshot of the iOS simulator" 2>&1)
    if echo "$result" | grep -q "agent-ios"; then
        echo "  ✓ Dry run works"
    else
        echo "  ✗ Dry run failed"
        echo "    Got: $result"
    fi
else
    echo "  - Skipped (no API key)"
fi

# Test 6: Raw tool access
echo "Test 6: --raw (direct tool access)"
result=$($AGENT_DO --raw tui list 2>&1)
if echo "$result" | grep -q -E "(No agent-tui sessions|Session)"; then
    echo "  ✓ Raw tool access works"
else
    echo "  ✗ Raw tool access failed"
    echo "    Got: $result"
fi

# Test 7: Pattern matcher
echo "Test 7: Pattern matcher JSON output"
result=$("$SCRIPT_DIR/bin/pattern-matcher" --json "click Save in Photoshop" 2>&1)
if echo "$result" | grep -q '"tool": "gui"'; then
    echo "  ✓ Pattern matcher works"
else
    echo "  ✗ Pattern matcher failed"
    echo "    Got: $result"
fi

echo
echo "Tests complete!"
