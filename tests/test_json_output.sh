#!/usr/bin/env bash
# lib/json-output.sh hands payloads to python on stdin, so a large result
# (e.g. ~1.7k vulnerability findings) no longer dies with
# "Argument list too long" before python runs. Also checks the envelopes.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/json-output.sh
source "$ROOT/lib/json-output.sh"

fail=0
check() { if eval "$2"; then echo "  ok $1"; else echo "  FAIL $1"; fail=1; fi; }

OUTPUT_FORMAT=json

big=$(python3 -c 'import json; print(json.dumps([{"id": i, "pad": "x" * 200} for i in range(15000)]))')
out=$(json_result "$big" 2>&1)
check "json_result handles a ${#big}-byte payload" \
    '[[ "$(printf "%s" "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[\"success\"], len(d[\"result\"]))")" == "True 15000" ]]'

out=$(json_success "$big" 2>&1)
check "json_success handles the same payload" \
    '[[ "$(printf "%s" "$out" | python3 -c "import json,sys; print(len(json.load(sys.stdin)[\"result\"]))")" == "15000" ]]'

lines=$(python3 -c 'print("\n".join("item-%d-%s" % (i, "y" * 100) for i in range(20000)))')
out=$(json_list "$lines" 2>&1)
check "json_list handles ${#lines} bytes" \
    '[[ "$(printf "%s" "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)[\"count\"])")" == "20000" ]]'

out=$(json_success "plain text, not JSON")
check "non-JSON text is wrapped as a string" \
    '[[ "$(printf "%s" "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)[\"result\"])")" == "plain text, not JSON" ]]'

OUTPUT_FORMAT=text
out=$(json_result '{"a":1}')
check "text mode pretty-prints JSON" '[[ "$out" == *"\"a\": 1"* ]]'

exit "$fail"
