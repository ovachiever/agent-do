#!/usr/bin/env python3
"""agent-render: db show / db connect-info / kv connect-info must mask passwords
unless --reveal is passed, and must honour --json.

Runs the real cmd_* functions against a stubbed render_request so no network
or API key is needed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PG_INFO = '{"id":"dpg-test","name":"test-db","status":"available","plan":"basic","region":"oregon","version":"16","createdAt":"2026-01-01T00:00:00Z"}'
PG_CONN = (
    '{"externalConnectionString":"postgresql://app:S3cr3tPg@host.render.com:5432/db",'
    '"internalConnectionString":"postgresql://app:S3cr3tPg@dpg-test-a/db",'
    '"password":"S3cr3tPg",'
    '"psqlCommand":"PGPASSWORD=S3cr3tPg psql -h host.render.com -p 5432 -U app db"}'
)
# env: a long secret, a short secret (<=8 chars — the old mask printed these in
# full), a short non-secret flag, a generated value, and an empty value.
ENV_VARS = (
    '[{"envVar":{"key":"API_KEY","value":"sk-proj-LongSecretValue123"}},'
    '{"envVar":{"key":"SHORT_PW","value":"Ab9xQ7"}},'
    '{"envVar":{"key":"FEATURE_FLAG","value":"1"}},'
    '{"envVar":{"key":"GEN_SECRET","value":"","generateValue":true}},'
    '{"envVar":{"key":"EMPTY_ONE","value":""}}]'
)
KV_CONN = (
    '{"cliCommand":" REDISCLI_AUTH=S3cr3tKv valkey-cli --user red-test -h kv.render.com -p 6379 --tls",'
    '"externalConnectionString":"rediss://red-test:S3cr3tKv@kv.render.com:6379",'
    '"internalConnectionString":"redis://red-test:6379"}'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cmd: str, render_json: str = "0") -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_postgres() {{ echo "dpg-test"; }}
resolve_kv() {{ echo "red-test"; }}
resolve_service() {{ echo "srv-test"; }}
render_request() {{
  case "$2" in
    /postgres/dpg-test) printf '%s\\n' '{PG_INFO}' ;;
    /postgres/dpg-test/connection-info) printf '%s\\n' '{PG_CONN}' ;;
    /key-value/red-test/connection-info) printf '%s\\n' '{KV_CONN}' ;;
    /services/srv-test/env-vars?limit=100) printf '%s\\n' '{ENV_VARS}' ;;
    *) echo "unexpected endpoint: $2" >&2; return 1 ;;
  esac
}}
RENDER_JSON={render_json}
{cmd}
"""
    return subprocess.run(["bash", "-lc", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    # db connect-info: masked by default, every line
    r = run("cmd_db_connect_info test-db")
    require(r.returncode == 0, f"connect-info failed: {r.stderr}")
    require("S3cr3tPg" not in r.stdout, f"password leaked in connect-info: {r.stdout}")
    require(r.stdout.count("***") == 3, f"expected 3 masked sites: {r.stdout}")
    require("PGPASSWORD=***" in r.stdout, f"PGPASSWORD not masked: {r.stdout}")

    # db connect-info --reveal: raw values
    r = run("cmd_db_connect_info test-db --reveal")
    require(r.returncode == 0, f"connect-info --reveal failed: {r.stderr}")
    require(r.stdout.count("S3cr3tPg") == 3, f"--reveal did not restore values: {r.stdout}")
    require("***" not in r.stdout, f"--reveal still masked: {r.stdout}")

    # db connect-info --json: JSON, masked including the bare password field
    r = run("cmd_db_connect_info test-db", render_json="1")
    require(r.returncode == 0, f"connect-info --json failed: {r.stderr}")
    require(r.stdout.lstrip().startswith("{"), f"--json did not emit JSON: {r.stdout}")
    require("S3cr3tPg" not in r.stdout, f"password leaked in --json: {r.stdout}")
    require('"password":"***"' in r.stdout, f"bare password field not masked: {r.stdout}")

    # db show: masked text; --json wraps both objects
    r = run("cmd_db show test-db")
    require(r.returncode == 0, f"db show failed: {r.stderr}")
    require("S3cr3tPg" not in r.stdout, f"password leaked in db show: {r.stdout}")
    require("Name:     test-db" in r.stdout, f"db show lost non-secret fields: {r.stdout}")
    r = run("cmd_db show test-db", render_json="1")
    require(r.returncode == 0, f"db show --json failed: {r.stderr}")
    require('"postgres"' in r.stdout and '"connectionInfo"' in r.stdout, f"db show --json shape: {r.stdout}")
    require("S3cr3tPg" not in r.stdout, f"password leaked in db show --json: {r.stdout}")
    r = run("cmd_db show test-db --reveal", render_json="1")
    require("S3cr3tPg" in r.stdout, f"db show --json --reveal did not reveal: {r.stdout}")

    # kv connect-info: REDISCLI_AUTH and rediss:// userinfo masked
    r = run("cmd_kv connect-info test-kv")
    require(r.returncode == 0, f"kv connect-info failed: {r.stderr}")
    require("S3cr3tKv" not in r.stdout, f"password leaked in kv connect-info: {r.stdout}")
    require("REDISCLI_AUTH=***" in r.stdout, f"REDISCLI_AUTH not masked: {r.stdout}")
    require("rediss://red-test:***@" in r.stdout, f"rediss userinfo not masked: {r.stdout}")
    r = run("cmd_kv connect-info test-kv --reveal")
    require(r.stdout.count("S3cr3tKv") == 2, f"kv --reveal did not restore: {r.stdout}")

    # env: every non-empty value fully masked by default — no prefix, no
    # short-value exemption (the old mask printed 4-char prefixes and any value <= 8 chars).
    secrets = ("sk-proj-LongSecretValue123", "Ab9xQ7")
    r = run("cmd_env test-svc")
    require(r.returncode == 0, f"env failed: {r.stderr}")
    for secret in secrets:
        require(secret not in r.stdout, f"env leaked a secret: {r.stdout}")
    require("sk-p" not in r.stdout, f"env leaked a secret prefix: {r.stdout}")
    for line in ("API_KEY=***", "SHORT_PW=***", "FEATURE_FLAG=***",
                 "GEN_SECRET=(generateValue)", "EMPTY_ONE=(empty)"):
        require(line in r.stdout.splitlines(), f"env missing {line!r}: {r.stdout}")

    # env --reveal: explicit opt-in prints values
    r = run("cmd_env test-svc --reveal")
    require(r.returncode == 0, f"env --reveal failed: {r.stderr}")
    for line in ("API_KEY=sk-proj-LongSecretValue123", "SHORT_PW=Ab9xQ7", "FEATURE_FLAG=1"):
        require(line in r.stdout.splitlines(), f"env --reveal missing {line!r}: {r.stdout}")

    # env --json: a JSON list, masked; never the raw API body
    r = run("cmd_env test-svc", render_json="1")
    require(r.returncode == 0, f"env --json failed: {r.stderr}")
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise AssertionError(f"env --json is not JSON: {r.stdout!r}")
    for secret in secrets:
        require(secret not in r.stdout, f"env --json leaked a secret: {r.stdout}")
    require('"envVar"' not in r.stdout, f"env --json passed the raw API body through: {r.stdout}")
    require(isinstance(data, list) and len(data) == 5, f"env --json shape: {data}")
    by_key = {item["key"]: item for item in data}
    require(by_key["API_KEY"]["value"] == "***" and by_key["SHORT_PW"]["value"] == "***",
            f"env --json not masked: {data}")
    require(by_key["GEN_SECRET"]["generateValue"] is True, f"env --json lost generateValue: {data}")
    require(by_key["EMPTY_ONE"]["value"] == "", f"env --json invented an empty value: {data}")

    # env --json --reveal
    r = run("cmd_env test-svc --reveal", render_json="1")
    by_key = {item["key"]: item for item in json.loads(r.stdout)}
    require(by_key["API_KEY"]["value"] == "sk-proj-LongSecretValue123", f"env --json --reveal: {r.stdout}")

    # env: unknown flags are refused (exit 2) — a silently ignored flag once
    # produced hashes of the mask string that looked like matching keys.
    r = run("cmd_env test-svc --bogus")
    require(r.returncode == 2, f"env accepted an unknown flag (rc={r.returncode}): {r.stdout}")
    for secret in secrets:
        require(secret not in r.stdout + r.stderr, f"env printed values on a bad flag: {r.stdout}")

    print("render db secrets tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
