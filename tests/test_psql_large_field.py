#!/usr/bin/env python3
"""psql query returns a field larger than Python csv's default 131072-byte limit.

2026-10-19: a json_agg of model rows made `agent-do psql query` crash with
"_csv.Error: field larger than field limit (131072)". The database call is
stubbed; the tool's own CSV-to-JSON parsing runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main Dispatcher ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-psql'}")
require_connection() {{ :; }}
_PG_DATABASE=testdb
snapshot_begin() {{ :; }}; snapshot_field() {{ :; }}; snapshot_end() {{ :; }}
run_psql_full() {{
  printf 'id,payload\\n1,"'
  python3 -c 'import sys; sys.stdout.write("x" * 300000)'
  printf '"\\n'
}}
cmd_query "select id, payload from big"
"""
    r = subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)
    out = r.stdout[r.stdout.index("{"):] if "{" in r.stdout else r.stdout
    # Some builds print a snapshot header first; the result is the last document.
    docs = []
    dec = json.JSONDecoder()
    i = 0
    while i < len(out):
        while i < len(out) and out[i].isspace():
            i += 1
        if i >= len(out):
            break
        doc, i = dec.raw_decode(out, i)
        docs.append(doc)
    result = docs[-1] if docs else {}
    if result.get("ok") is not True or len(result["rows"][0][1]) != 300000:
        raise AssertionError(f"large field not returned: rc={r.returncode} stderr={r.stderr[-300:]!r}")
    print("psql large-field test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
