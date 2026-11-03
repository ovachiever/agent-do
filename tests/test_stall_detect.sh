#!/usr/bin/env bash
# stall_detect returns as soon as its command does, passes output and exit
# status through, and still aborts a command that overruns the limit.
# Before the fix a 0 s command took >=5 s (fixed `sleep 5` before the first
# liveness check), which made every agent-sentry API call cost 5 s or more.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/retry.sh
source "$ROOT/lib/retry.sh"

fail=0
check() { if eval "$2"; then echo "  ok $1"; else echo "  FAIL $1"; fail=1; fi; }

now_ms() { python3 -c 'import time; print(int(time.time()*1000))'; }

start=$(now_ms)
out=$(stall_detect 10 echo hello)
status=$?
elapsed=$(( $(now_ms) - start ))
check "fast command returns quickly (${elapsed} ms)" '[[ $elapsed -lt 2000 ]]'
check "output passes through" '[[ "$out" == "hello" ]]'
check "success status passes through" '[[ $status -eq 0 ]]'

stall_detect 10 false
status=$?
check "failure status passes through" '[[ $status -eq 1 ]]'

start=$(now_ms)
stall_detect 2 sleep 30 2>/dev/null
status=$?
elapsed=$(( $(now_ms) - start ))
check "overrunning command is aborted (${elapsed} ms)" '[[ $status -ne 0 && $elapsed -lt 5000 ]]'

exit "$fail"
