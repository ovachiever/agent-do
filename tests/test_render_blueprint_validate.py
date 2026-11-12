#!/usr/bin/env python3
"""agent-render blueprint validate must POST multipart/form-data with the two
fields the API requires (ownerId, file) — not a JSON body — and must exit 2
when the file is invalid.

Contract: https://api-docs.render.com/reference/validate-blueprint
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(yaml_path: str, response: str, extra: str = "", render_json: str = "0") -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
export RENDER_API_KEY=test-key
default_owner_id() {{ echo "tea-test"; }}
resolve_owner() {{ echo "$1"; }}
render_request() {{ echo "UNEXPECTED_JSON_REQUEST $1 $2" >&2; return 1; }}
render_request_checked() {{ echo "UNEXPECTED_JSON_REQUEST $1 $2" >&2; return 1; }}
curl() {{
  printf 'CURL_ARGS:' >&2; printf ' %q' "$@" >&2; printf '\\n' >&2
  local out="" i j
  for ((i=1;i<=$#;i++)); do [[ "${{!i}}" == "-o" ]] && {{ j=$((i+1)); out="${{!j}}"; }}; done
  printf '%s' '{response}' > "$out"
  printf '200'
}}
RENDER_JSON={render_json}
cmd_blueprint validate "{yaml_path}" {extra}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    tmp.write("services:\n  - name: x\n    type: web\n")
    tmp.close()

    r = run(tmp.name, '{"valid":true,"plan":{"totalActions":2,"services":[{"action":"create","name":"x"}]}}')
    require(r.returncode == 0, f"valid file should exit 0: rc={r.returncode} {r.stderr}")
    require("UNEXPECTED_JSON_REQUEST" not in r.stderr, f"validate went through the JSON helper: {r.stderr}")
    require("-F ownerId=tea-test" in r.stderr, f"ownerId multipart field missing: {r.stderr}")
    require(f"-F file=@{tmp.name}" in r.stderr, f"file multipart field missing: {r.stderr}")
    require("Content-Type" not in r.stderr, f"must not force a JSON Content-Type on multipart: {r.stderr}")
    require("/blueprints/validate" in r.stderr, f"wrong endpoint: {r.stderr}")
    require("valid: True" in r.stdout and "plan: 2 action(s)" in r.stdout and "services: create x" in r.stdout,
            f"unexpected text output: {r.stdout}")

    r = run(tmp.name, '{"valid":false,"errors":[{"line":3,"column":5,"path":"services[0]","error":"unknown type"}]}')
    require(r.returncode == 2, f"invalid file should exit 2: rc={r.returncode} {r.stderr}")
    require("error: unknown type  (line:col 3:5  path services[0])" in r.stdout, f"error line format: {r.stdout}")

    r = run(tmp.name, '{"valid":true,"plan":{"totalActions":0}}', extra="--owner tea-other")
    require("-F ownerId=tea-other" in r.stderr, f"--owner not honoured: {r.stderr}")

    r = run(tmp.name, '{"valid":true,"plan":{"totalActions":0}}', render_json="1")
    require(r.stdout.strip().startswith('{"valid":true'), f"--json should pass the raw response: {r.stdout}")

    r = run(tmp.name, "{}", extra="--bogus")
    require(r.returncode == 1 and "unknown option" in r.stderr, f"unknown flag handling: {r.stderr}")

    Path(tmp.name).unlink()
    print("render blueprint validate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
