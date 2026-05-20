#!/usr/bin/env python3
"""Tests for agent-psql — PostgreSQL CLI wrapper for AI agents.

Covers: help output, status, profiles, table name validation,
connection string parsing/masking, error paths. No live database required.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-psql"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_tool(*args: str, env_override: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
        if "HOME" in env_override and "AGENT_DO_HOME" not in env_override:
            env["AGENT_DO_HOME"] = str(Path(env_override["HOME"]) / ".agent-do")
    return subprocess.run(
        [str(TOOL), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run_bash(script: str, env_override: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
        if "HOME" in env_override and "AGENT_DO_HOME" not in env_override:
            env["AGENT_DO_HOME"] = str(Path(env_override["HOME"]) / ".agent-do")
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    failures = 0

    def check(name: str, fn):
        nonlocal failures
        try:
            fn()
            print(f"  PASS: {name}")
        except AssertionError as e:
            print(f"  FAIL: {name}: {e}")
            failures += 1

    # ---- Help ----
    def test_help():
        r = run_tool("help")
        require(r.returncode == 0, f"help failed: {r.stderr}")
        require("agent-psql" in r.stdout, f"help missing tool name: {r.stdout[:200]}")
        require("connect" in r.stdout, "help missing connect command")
        require("snapshot" in r.stdout, "help missing snapshot command")
        require("query" in r.stdout, "help missing query command")
        require("dump" in r.stdout, "help missing dump command")
        require("EXIT CODES" in r.stdout, "help missing exit codes section")

    check("help output", test_help)

    def test_help_via_flag():
        r = run_tool("--help")
        require(r.returncode == 0, f"--help failed: {r.stderr}")
        require("agent-psql" in r.stdout, "--help missing tool name")

    check("--help flag", test_help_via_flag)

    # ---- Status (no connection) ----
    def test_status_disconnected():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("status", env_override=env)
            require(r.returncode == 0, f"status failed: {r.stderr}")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"status not ok: {data}")
            require(data["connected"] is False, f"status should be disconnected: {data}")

    check("status when disconnected", test_status_disconnected)

    # ---- Profiles ----
    def test_profiles_empty():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("profiles", env_override=env)
            require(r.returncode == 0, f"profiles failed: {r.stderr}")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"profiles not ok: {data}")
            require(data["count"] == 0, f"expected 0 profiles: {data}")

    check("profiles empty list", test_profiles_empty)

    def test_profile_add_and_list():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            # Use a passwordless connection string to avoid Keychain prompts in test
            r = run_tool("profile", "add", "testdb",
                         "postgresql://myuser@db.render.com:5432/mydb?sslmode=require",
                         env_override=env)
            require(r.returncode == 0, f"profile add failed: {r.stderr}")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"profile add not ok: {data}")

            # Verify profiles file was created
            profiles_file = Path(tmpdir) / ".agent-do" / "psql" / "profiles.json"
            require(profiles_file.exists(), "profiles file not created")

            # List profiles
            r2 = run_tool("profiles", env_override=env)
            data2 = json.loads(r2.stdout)
            require(data2["count"] == 1, f"expected 1 profile: {data2}")
            require(data2["profiles"][0]["name"] == "testdb", f"wrong name: {data2}")
            require(data2["profiles"][0]["database"] == "mydb", f"wrong database: {data2}")

    check("profile add and list", test_profile_add_and_list)

    def test_profile_remove():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            run_tool("profile", "add", "tempdb",
                     "postgresql://u@h:5432/d", env_override=env)
            r = run_tool("profile", "remove", "tempdb", env_override=env)
            require(r.returncode == 0, f"profile remove failed: {r.stderr}")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"profile remove not ok: {data}")
            # Verify removed
            r2 = run_tool("profiles", env_override=env)
            data2 = json.loads(r2.stdout)
            require(data2["count"] == 0, f"profile not removed: {data2}")

    check("profile remove", test_profile_remove)

    def test_profile_remove_nonexistent():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("profile", "remove", "ghost", env_override=env)
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"should fail for nonexistent: {data}")

    check("profile remove nonexistent", test_profile_remove_nonexistent)

    # ---- Table Name Validation ----
    def test_validate_table_name_valid():
        script = f'''
source "{TOOL}"  # won't execute main — functions only via source
validate_table_name "users" && echo "VALID"
validate_table_name "my_table" && echo "VALID"
validate_table_name "schema.table_name" && echo "VALID"
validate_table_name "_private" && echo "VALID"
'''
        # Source won't work since the file has a case dispatch at bottom.
        # Instead, extract the function and test it directly.
        script = f'''
eval "$(sed -n '/^validate_table_name/,/^}}/p' "{TOOL}")"
validate_table_name "users" && echo "VALID:users"
validate_table_name "my_table" && echo "VALID:my_table"
validate_table_name "public.users" && echo "VALID:public.users"
validate_table_name "_private" && echo "VALID:_private"
validate_table_name "CamelCase123" && echo "VALID:CamelCase123"
'''
        r = run_bash(script)
        for name in ["users", "my_table", "public.users", "_private", "CamelCase123"]:
            require(f"VALID:{name}" in r.stdout, f"'{name}' should be valid: {r.stdout}")

    check("validate_table_name accepts valid names", test_validate_table_name_valid)

    def test_validate_table_name_invalid():
        script = f'''
eval "$(sed -n '/^validate_table_name/,/^}}/p' "{TOOL}")"
validate_table_name "users; DROP TABLE x" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:injection"
validate_table_name "table'name" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:quote"
validate_table_name "" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:empty"
validate_table_name "table name" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:space"
validate_table_name "1starts_with_digit" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:digit"
validate_table_name "a.b.c" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:multidot"
validate_table_name "schema.1bad" 2>/dev/null && echo "ACCEPTED" || echo "REJECTED:schema_bad_table"
'''
        r = run_bash(script)
        for case in ["injection", "quote", "empty", "space", "digit", "multidot", "schema_bad_table"]:
            require(f"REJECTED:{case}" in r.stdout, f"'{case}' should be rejected: {r.stdout}")
        # Verify no invalid names were accepted
        require("ACCEPTED" not in r.stdout, "some invalid names were accepted")

    check("validate_table_name rejects invalid names", test_validate_table_name_invalid)

    def test_parse_table_ref():
        script = f'''
eval "$(sed -n '/^parse_table_ref/,/^}}/p' "{TOOL}")"
parse_table_ref "users"
echo "SCHEMA:$_TBL_SCHEMA TABLE:$_TBL_NAME"
parse_table_ref "myschema.mytable"
echo "SCHEMA:$_TBL_SCHEMA TABLE:$_TBL_NAME"
parse_table_ref "public.accounts"
echo "SCHEMA:$_TBL_SCHEMA TABLE:$_TBL_NAME"
'''
        r = run_bash(script)
        require("SCHEMA:public TABLE:users" in r.stdout, f"bare name should default to public schema: {r.stdout}")
        require("SCHEMA:myschema TABLE:mytable" in r.stdout, f"schema.table should parse correctly: {r.stdout}")
        require("SCHEMA:public TABLE:accounts" in r.stdout, f"public.accounts should parse correctly: {r.stdout}")

    check("parse_table_ref splits schema and table", test_parse_table_ref)

    # ---- Connection String Masking ----
    def test_mask_connection_string():
        script = f'''
eval "$(sed -n '/^mask_connection_string/,/^}}/p' "{TOOL}")"
mask_connection_string "postgresql://myuser:supersecret@db.render.com:5432/mydb"
'''
        r = run_bash(script)
        out = r.stdout.strip()
        require("supersecret" not in out, f"password not masked: {out}")
        require("myuser" in out, f"username missing: {out}")
        require("db.render.com" in out, f"host missing: {out}")
        require("mydb" in out, f"database missing: {out}")

    check("mask_connection_string redacts password", test_mask_connection_string)

    # ---- Connect Error Paths ----
    def test_connect_no_args():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            # Unset all PG* vars (pop, not empty string — empty is still "set")
            for k in ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPORT"]:
                env.pop(k, None)
            r = run_tool("connect", env_override=env)
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"connect with no args should fail: {data}")

    check("connect with no args fails", test_connect_no_args)

    def test_connect_bad_host():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("connect",
                         "postgresql://u:p@nonexistent.invalid:5432/db",
                         env_override=env)
            require(r.returncode != 0, "connect to nonexistent host should fail")
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"should report failure: {data}")

    check("connect to bad host fails cleanly", test_connect_bad_host)

    # ---- Unknown Command ----
    def test_unknown_command():
        r = run_tool("bogus_command_xyz")
        data = json.loads(r.stdout)
        require(data["ok"] is False, f"unknown command should fail: {data}")
        require("Unknown command" in data.get("error", ""), f"wrong error: {data}")

    check("unknown command returns error JSON", test_unknown_command)

    # ---- Disconnect When Not Connected ----
    def test_disconnect_clean():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("disconnect", env_override=env)
            require(r.returncode == 0, f"disconnect failed: {r.stderr}")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"disconnect not ok: {data}")

    check("disconnect when not connected", test_disconnect_clean)

    # ---- Commands Requiring Connection Fail Cleanly ----
    def test_snapshot_no_connection():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("snapshot", env_override=env)
            require(r.returncode != 0, "snapshot without connection should fail")
            # Error goes to stdout as JSON
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"should report not connected: {data}")
            require("Not connected" in data.get("error", ""), f"wrong error: {data}")

    check("snapshot without connection", test_snapshot_no_connection)

    def test_query_no_connection():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("query", "SELECT 1", env_override=env)
            require(r.returncode != 0, "query without connection should fail")
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"should report not connected: {data}")

    check("query without connection", test_query_no_connection)

    def test_describe_no_connection():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"HOME": tmpdir}
            r = run_tool("describe", "users", env_override=env)
            require(r.returncode != 0, "describe without connection should fail")
            data = json.loads(r.stdout)
            require(data["ok"] is False, f"should report not connected: {data}")

    check("describe without connection", test_describe_no_connection)

    # ---- Summary ----
    print(f"\npsql tests: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
