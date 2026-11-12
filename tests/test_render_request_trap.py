#!/usr/bin/env python3
"""agent-render render_request_checked: no RETURN trap may leak into the caller.

The helper used `trap 'rm -f "$tmp_body"' RETURN`. Bash RETURN traps are not
function-scoped: the trap survives the helper's return and fires again when
the *calling* function returns, by which time the helper's `local tmp_body`
is gone — under `set -u` that is `tmp_body: unbound variable` on stderr after
an otherwise-successful call. Only direct callers (not `$(...)`/pipes) see it,
which is every mutating verb (delete, cron run, rollback, ...).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
export RENDER_API_KEY=test-key
curl() {{
  # emulate: write body to the -o path, print 200 on stdout
  local out=""; local i
  for ((i=1;i<=$#;i++)); do [[ "${{!i}}" == "-o" ]] && {{ j=$((i+1)); out="${{!j}}"; }}; done
  printf '%s' '{{"ok":true}}' > "$out"
  printf '200'
}}
caller_verb() {{
  render_request_checked DELETE "/services/srv-test" > /dev/null && echo "Deleted"
}}
caller_verb
echo "AFTER_CALLER"
"""
    r = subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)
    require(r.returncode == 0, f"harness failed: rc={r.returncode} stderr={r.stderr}")
    require("Deleted" in r.stdout and "AFTER_CALLER" in r.stdout, f"unexpected stdout: {r.stdout}")
    require("tmp_body" not in r.stderr, f"RETURN trap leaked into caller: {r.stderr}")
    require(r.stderr.strip() == "", f"unexpected stderr: {r.stderr}")
    print("render request-helper trap tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
