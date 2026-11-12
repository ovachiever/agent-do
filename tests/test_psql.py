#!/usr/bin/env python3
"""Tests for agent-psql — PostgreSQL CLI wrapper for AI agents.

Covers: help output, status, profiles, table name validation,
connection string parsing/masking, error paths. No live database required.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote_from_bytes

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-psql"
KEYCHAIN_HELPER = ROOT / "lib" / "psql_keychain_store.py"


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


def load_keychain_helper():
    spec = importlib.util.spec_from_file_location("psql_keychain_store", KEYCHAIN_HELPER)
    require(spec is not None and spec.loader is not None, "keychain helper is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        tool_text = TOOL.read_text()
        remove_body = tool_text.split("cmd_profile_remove() {", 1)[1].split("\n}", 1)[0]
        require(
            "_run_keychain_helper --profile-remove" in remove_body,
            "profile removal bypasses the locked helper transaction",
        )
        require("/usr/bin/security" not in remove_body, "profile removal test could reach the real Keychain")
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

    # ---- macOS Keychain storage (all tests use fakes; never the real Keychain) ----
    def test_keychain_command_uses_stdin_not_argv():
        helper = load_keychain_helper()
        calls = []

        class RecordingStream(io.BytesIO):
            requested_size = None

            def read(self, size=-1):
                self.requested_size = size
                return super().read(size)

        def fake_runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        account = 'profile with space "quote" \\ slash'
        secret = b'synthetic password\r\nwith spaces "quotes" and \\slashes'
        stream = RecordingStream(secret)
        previous_pgpassword = os.environ.get("PGPASSWORD")
        os.environ["PGPASSWORD"] = secret.decode()
        try:
            exit_code = helper.main(
                [account], stdin=stream, runner=fake_runner, platform_name="darwin"
            )
        finally:
            if previous_pgpassword is None:
                os.environ.pop("PGPASSWORD", None)
            else:
                os.environ["PGPASSWORD"] = previous_pgpassword

        require(exit_code == 0, "successful helper invocation should report success")
        require(
            stream.requested_size == helper.SECURITY_INPUT_LIMIT + 1,
            f"helper stdin read was not bounded: {stream.requested_size}",
        )
        require(len(calls) == 1, f"expected one security invocation, got {len(calls)}")
        argv, kwargs = calls[0]
        require(argv == ["/usr/bin/security", "-i", "-q"], f"unsafe security argv: {argv}")
        argv_bytes = "\0".join(argv).encode()
        require(secret not in argv_bytes, "raw secret reached process argv")
        require(secret.hex().encode() not in argv_bytes, "hex secret reached process argv")

        expected_account = '"profile with space \\"quote\\" \\\\ slash"'
        expected = (
            "add-generic-password -U -a "
            f"{expected_account} -s \"agent-psql\" -X {secret.hex()}\n"
        ).encode()
        require(kwargs.get("input") == expected, f"unexpected security stdin: {kwargs.get('input')!r}")
        require(expected.count(b"\n") == 1, "security input must contain exactly one command line")
        require(secret not in expected, "raw secret reached SecurityTool input instead of hex")
        require(kwargs.get("stdout") == subprocess.DEVNULL, "security stdout must be suppressed")
        require(kwargs.get("stderr") == subprocess.DEVNULL, "security stderr must be suppressed")
        require(kwargs.get("check") is False, "security status must be handled explicitly")
        require(
            kwargs.get("timeout") == helper.SECURITY_TIMEOUT_SECONDS,
            f"security execution was not bounded: {kwargs.get('timeout')}",
        )
        child_env = kwargs.get("env")
        require(isinstance(child_env, dict), "security child environment must be explicit")
        require("PGPASSWORD" not in child_env, "ambient PGPASSWORD reached SecurityTool environment")
        require(secret.decode() not in child_env.values(), "raw secret reached SecurityTool environment")

    check("keychain secret is stdin-only and account quoting is exact", test_keychain_command_uses_stdin_not_argv)

    def test_profile_uri_is_stdin_only_and_password_bytes_are_exact():
        helper = load_keychain_helper()
        secret = b"A" * 160 + b"\x1f\n\n"
        encoded = quote_from_bytes(secret)
        raw_uri = f"postgresql://user:{encoded}@[2001:db8::1]:5432/db?sslmode=require".encode()
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            status, credential_required = helper.store_profile_uri(
                "profile",
                raw_uri,
                profiles_path,
                runner=fake_runner,
                platform_name="darwin",
            )
            require(status == helper.PROFILE_STORE_OK and credential_required, f"URI store failed: {status}")
            require(len(calls) == 1, f"unexpected SecurityTool call count: {calls}")
            command = calls[0][1].get("input", b"")
            require(f"-X {secret.hex()}\n".encode() in command, "percent-encoded password lost bytes")
            record = json.loads(profiles_path.read_text())["profile"]
            require(record["credential_required"] is True, "profile lost credential binding")
            require(
                record["connection_string"]
                == "postgresql://user:****@[2001:db8::1]:5432/db?sslmode=require",
                f"masked URI drifted: {record}",
            )
            require(encoded not in profiles_path.read_text(), "encoded password reached profile state")

            before = profiles_path.read_bytes()
            query_passwords = [
                b"postgresql://user@db.invalid/d?password=query-secret",
                b"postgresql://user@db.invalid/d?pass%77ord=query-secret",
                b"postgresql://user@db.invalid/d?PASSWORD=query-secret",
                b"postgresql://user@db.invalid/d?sslpassword=query-secret",
                b"postgresql://user@db.invalid/d?SSL%70ASSWORD=query-secret",
                b"host=db.invalid dbname=d user=user password=query-secret",
                b"postgresql://user:synthetic-secret/db",
            ]
            for query_uri in query_passwords:
                query_status, _ = helper.store_profile_uri(
                    "query-secret",
                    query_uri,
                    profiles_path,
                    runner=fake_runner,
                    platform_name="darwin",
                )
                require(
                    query_status == helper.PROFILE_STATE_FAILURE,
                    f"query password bypass was accepted: {query_uri!r}",
                )
                require(profiles_path.read_bytes() == before, "query password changed profile state")
            require(len(calls) == 1, "query password reached SecurityTool")

            oversized = b"p" * (helper.PROFILE_INPUT_LIMIT + 1)
            require(
                helper.main(
                    ["--profile-uri", "too-large", str(profiles_path)],
                    stdin=io.BytesIO(oversized),
                    runner=fake_runner,
                    platform_name="darwin",
                )
                == helper.PROFILE_STATE_FAILURE,
                "oversized profile URI was accepted",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            captured_argv = Path(tmpdir) / "argv"
            captured_stdin = Path(tmpdir) / "stdin"
            captured_setup_env = Path(tmpdir) / "setup-env"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
export conn_string=ambient-export-marker
source "{TOOL}" help >/dev/null
ensure_config_dir() {{ /usr/bin/env > "{captured_setup_env}"; }}
_run_keychain_helper() {{
    builtin printf '%s\\0' "$@" > "{captured_argv}"
    cat > "{captured_stdin}"
    return 0
}}
cmd_profile_add profile '{raw_uri.decode()}' >/dev/null
'''
            result = run_bash(script)
            require(result.returncode == 0, f"profile stdin bridge failed: {result.stderr}")
            argv_bytes = captured_argv.read_bytes()
            require(raw_uri not in argv_bytes, "raw profile URI reached helper argv")
            require(
                argv_bytes.split(b"\0")[:-1][0] == b"--profile-uri",
                f"profile helper mode drifted: {argv_bytes!r}",
            )
            require(captured_stdin.read_bytes() == raw_uri, "profile URI stdin was not byte-exact")
            setup_env = captured_setup_env.read_bytes()
            require(b"conn_string=" not in setup_env, "profile URI holder reached the setup child environment")
            require(raw_uri not in setup_env, "raw profile URI reached the setup child environment")

    check(
        "profile URI stays on stdin and percent-decoded password bytes are exact",
        test_profile_uri_is_stdin_only_and_password_bytes_are_exact,
    )

    def test_profile_uri_matches_wrapper_endpoint_contract():
        helper = load_keychain_helper()
        accepted = {
            b"postgresql:///d": ("postgresql:///d", b"", False),
            b"postgresql://user@/d": ("postgresql://user@/d", b"", False),
            b"postgresql://user:synthetic@/d": (
                "postgresql://user:****@/d",
                b"synthetic",
                True,
            ),
            b"postgresql://host:5432/d": ("postgresql://host:5432/d", b"", False),
            b"postgresql://host1,host2/d": (
                "postgresql://host1,host2/d",
                b"",
                False,
            ),
            b"postgresql://[2001:db8::1]:5432/d": (
                "postgresql://[2001:db8::1]:5432/d",
                b"",
                False,
            ),
        }
        for raw_uri, expected in accepted.items():
            require(helper._parse_profile_uri(raw_uri) == expected, f"supported endpoint drifted: {raw_uri!r}")

        rejected = [
            b"postgresql://user:synthetic-secret/db",
            b"postgresql://host:65536/d",
            b"postgresql://host1:5432,host2:5433/d",
        ]
        for raw_uri in rejected:
            try:
                helper._parse_profile_uri(raw_uri)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsupported endpoint was accepted: {raw_uri!r}")

    check(
        "profile URI enforces the wrapper-supported endpoint contract",
        test_profile_uri_matches_wrapper_endpoint_contract,
    )

    def test_profile_uri_preserves_nonmac_profile_behavior():
        helper = load_keychain_helper()
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            status, credential_required = helper.store_profile_uri(
                "linux-profile",
                b"postgresql://user:synthetic@db.invalid/d",
                profiles_path,
                runner=fake_runner,
                platform_name="linux",
            )
            require(status == helper.PROFILE_STORE_OK, f"non-mac profile add regressed: {status}")
            require(credential_required is True, "non-mac profile lost its historical credential expectation")
            require(calls == [], "non-mac profile add invoked SecurityTool")
            record = json.loads(profiles_path.read_text())["linux-profile"]
            require(record["connection_string"] == "postgresql://user:****@db.invalid/d", record)
            require(record["credential_required"] is True, record)

    check(
        "profile URI preserves the non-mac masked-profile no-op behavior",
        test_profile_uri_preserves_nonmac_profile_behavior,
    )

    def test_profile_messages_are_json_safe_for_quoted_names():
        with tempfile.TemporaryDirectory() as tmpdir:
            name = 'quoted"name\\path'
            env = {"HOME": tmpdir}
            added = run_tool(
                "profile",
                "add",
                name,
                "postgresql://u@db.invalid/d",
                env_override=env,
            )
            require(added.returncode == 0, f"quoted profile add failed: {added.stderr}")
            require(json.loads(added.stdout)["ok"] is True, f"add emitted invalid JSON: {added.stdout!r}")

            duplicate = run_tool(
                "profile",
                "add",
                name,
                "postgresql://u@other.invalid/d",
                env_override=env,
            )
            require(duplicate.returncode != 0, "duplicate quoted profile was accepted")
            duplicate_json = json.loads(duplicate.stdout)
            require(duplicate_json["ok"] is False and name in duplicate_json["error"], duplicate_json)

            removed = run_tool("profile", "remove", name, env_override=env)
            require(removed.returncode == 0, f"quoted profile remove failed: {removed.stderr}")
            require(json.loads(removed.stdout)["ok"] is True, f"remove emitted invalid JSON: {removed.stdout!r}")

            missing = run_tool("profile", "remove", name, env_override=env)
            require(missing.returncode != 0, "missing quoted profile removal succeeded")
            missing_json = json.loads(missing.stdout)
            require(missing_json["ok"] is False and name in missing_json["error"], missing_json)

            profiles_file = Path(tmpdir) / ".agent-do" / "psql" / "profiles.json"
            profiles_file.write_text(
                json.dumps(
                    {
                        name: {
                            "connection_string": "postgresql://u:****@db.invalid/d",
                            "credential_required": True,
                        }
                    }
                )
            )
            script = f'''
export AGENT_DO_HOME="{tmpdir}/.agent-do"
source "{TOOL}" help >/dev/null
ensure_psql() {{ :; }}
_run_keychain_helper() {{
    if [[ "$1" == "--read" ]]; then return 1; fi
    command python3 "${{SCRIPT_DIR}}/../lib/psql_keychain_store.py" "$@"
}}
cmd_connect --profile '{name}'
'''
            unavailable = run_bash(script)
            require(unavailable.returncode != 0, "missing quoted credential connect succeeded")
            unavailable_json = json.loads(unavailable.stdout)
            require(
                unavailable_json["ok"] is False and name in unavailable_json["error"],
                unavailable_json,
            )

    check(
        "profile result messages JSON-encode quoted names",
        test_profile_messages_are_json_safe_for_quoted_names,
    )

    def test_keychain_reader_decodes_binary_and_preserves_printable_hex():
        helper = load_keychain_helper()
        binary_secret = b"A" * 160 + b"\nline with spaces and \\slashes"
        binary_calls = []

        def binary_runner(argv, **kwargs):
            binary_calls.append((argv, kwargs))
            detail = b'password: 0x' + binary_secret.hex().encode() + b'  "display"\n'
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=detail)

        actual_binary = helper.read_password("binary account", runner=binary_runner)
        require(actual_binary == binary_secret, "binary Keychain password did not decode byte-exactly")
        require(len(binary_calls) == 1 and binary_calls[0][0][-1] == "-g", "binary read used an ambiguous -w path")

        printable_secret = b"deadbeef" * 24
        printable_calls = []

        def printable_runner(argv, **kwargs):
            printable_calls.append((argv, kwargs))
            if argv[-1] == "-g":
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=b"",
                    stderr=b'password: "' + printable_secret + b'"\n',
                )
            return subprocess.CompletedProcess(argv, 0, stdout=printable_secret + b"\n", stderr=b"")

        actual_printable = helper.read_password("printable account", runner=printable_runner)
        require(actual_printable == printable_secret, "printable hex-looking password was mis-decoded")
        require([call[0][-1] for call in printable_calls] == ["-g", "-w"], "printable read classification drifted")
        for _, kwargs in [*binary_calls, *printable_calls]:
            require(kwargs.get("timeout") == helper.SECURITY_TIMEOUT_SECONDS, "Keychain read was unbounded")
            require("PGPASSWORD" not in kwargs.get("env", {}), "Keychain read inherited PGPASSWORD")

    check(
        "keychain reader decodes binary and preserves printable hex passwords",
        test_keychain_reader_decodes_binary_and_preserves_printable_hex,
    )

    def test_keychain_bash_bridge_uses_helper_stdin_and_preserves_nonmac_noop():
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bin = Path(tmpdir) / "bin"
            fake_bin.mkdir()
            captured = Path(tmpdir) / "helper-stdin"
            captured_argv = Path(tmpdir) / "helper-argv"
            helper_calls = Path(tmpdir) / "helper-calls"
            session_key_called = Path(tmpdir) / "session-key-called"
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                """#!/bin/bash
if [[ -n "${PGPASSWORD+x}${_PG_PASSWORD+x}${password+x}${keychain_secret+x}${pgpassword_value+x}${conn_string+x}${stored_pw+x}" ]]; then
    exit 70
fi
printf 'x' >> "$HELPER_CALLS"
if [[ ! -e "$HELPER_ARGV_CAPTURE" ]]; then
    printf '%s\\0' "$@" > "$HELPER_ARGV_CAPTURE"
    cat > "$HELPER_STDIN_CAPTURE"
else
    cat > /dev/null
fi
"""
            )
            fake_python.chmod(0o700)
            account = 'profile with space "quote" \\ slash'
            secret = "synthetic password\nwith spaces"
            script = f'''
source "{TOOL}" help >/dev/null
export PATH="{fake_bin}:$PATH"
export HELPER_ARGV_CAPTURE="{captured_argv}"
export HELPER_STDIN_CAPTURE="{captured}"
export HELPER_CALLS="{helper_calls}"
password=$'synthetic password\nwith spaces'
export PGPASSWORD="$password"
export _PG_PASSWORD="$password"
export password pgpassword_value="$password" conn_string="$password" stored_pw="$password"
_store_password '{account}' "$password"
if declare -p PGPASSWORD >/dev/null 2>&1; then exit 45; fi

# Session-key construction must not fork before the writer scrubs its children.
export PGPASSWORD="$password"
_PG_HOST='db.invalid'
_PG_PORT='5432'
_PG_USER='user'
_PG_DATABASE='db'
_session_key() {{
    : > "{session_key_called}"
    printf 'unexpected-session-key'
}}
_store_session_password "$password"
if declare -p PGPASSWORD >/dev/null 2>&1; then exit 49; fi

# A shell-only PGPASSWORD is also consumed inside the short-lived macOS CLI.
PGPASSWORD="$password"
export -n PGPASSWORD
_store_password 'shell-only' "$password"
if declare -p PGPASSWORD >/dev/null 2>&1; then exit 46; fi

# Preserve an unset caller variable exactly.
unset PGPASSWORD
_store_password 'unset' "$password"
if declare -p PGPASSWORD >/dev/null 2>&1; then exit 47; fi

'''
            r = run_bash(script)
            require(r.returncode == 0, f"keychain Bash bridge failed: {r.stderr}")
            require(captured.read_text() == secret, "Bash bridge did not pass the exact secret on stdin")
            argv_bytes = captured_argv.read_bytes()
            require(secret.encode() not in argv_bytes, "raw secret reached helper process argv")
            require(secret.encode().hex().encode() not in argv_bytes, "hex secret reached helper process argv")
            require(
                argv_bytes.split(b"\0")[:-1]
                == [
                    f"{TOOL.parent}/../lib/psql_keychain_store.py".encode(),
                    account.encode(),
                ],
                f"unexpected helper argv: {argv_bytes!r}",
            )
            require(not session_key_called.exists(), "session key was built in a pre-store command substitution")
            require(helper_calls.read_text() == "xxxx", "unexpected Keychain helper invocation count")

    check(
        "keychain Bash bridge scrubs child argv and environment",
        test_keychain_bash_bridge_uses_helper_stdin_and_preserves_nonmac_noop,
    )

    def test_readonly_pgpassword_fails_before_platform_or_helper():
        with tempfile.TemporaryDirectory() as tmpdir:
            helper_marker = Path(tmpdir) / "helper-called"
            script = f'''
source "{TOOL}" help >/dev/null
_run_keychain_helper() {{ : > "{helper_marker}"; return 0; }}
export PGPASSWORD='synthetic-readonly-secret'
readonly PGPASSWORD
if _store_password account 'synthetic-readonly-secret'; then
    exit 90
else
    printf 'status=%s' "$?"
fi
'''
            r = run_bash(script)
            require(r.returncode == 0, f"readonly PGPASSWORD harness failed: {r.stderr}")
            require(r.stdout == "status=1", f"readonly PGPASSWORD failure was unstable: {r.stdout!r}")
            require(r.stderr == "", f"readonly PGPASSWORD leaked a shell error: {r.stderr!r}")
            require(not helper_marker.exists(), "Keychain helper ran with an unsanitized readonly secret")

    check(
        "readonly PGPASSWORD fails before platform or helper execution",
        test_readonly_pgpassword_fails_before_platform_or_helper,
    )

    def test_platform_decision_uses_python_runtime_not_ostype():
        helper = load_keychain_helper()
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        linux_status = helper.main(
            ["account"],
            stdin=io.BytesIO(b"synthetic"),
            runner=fake_runner,
            platform_name="linux",
        )
        require(linux_status == 0, "non-mac helper path did not preserve the no-op contract")
        require(calls == [], "non-mac helper path invoked SecurityTool")

        darwin_status = helper.main(
            ["account"],
            stdin=io.BytesIO(b"synthetic"),
            runner=fake_runner,
            platform_name="darwin",
        )
        require(darwin_status == 0 and len(calls) == 1, "Darwin helper path skipped storage")

    check(
        "platform decision uses the Python runtime instead of OSTYPE",
        test_platform_decision_uses_python_runtime_not_ostype,
    )

    def test_keychain_command_rejects_injection_and_parser_overflow():
        helper = load_keychain_helper()
        calls = []

        def fake_runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        for account in ["line\nfeed", "carriage\rreturn", "nul\0byte", ""]:
            require(
                helper.store_password(account, b"synthetic", runner=fake_runner) is False,
                f"unsafe account accepted: {account!r}",
            )
        require(calls == [], "invalid accounts must fail before security execution")

        # Find an account length whose fixed command overhead allows an exact
        # 4,096-byte command-plus-newline boundary with a whole-byte secret.
        for account_length in range(1, 8):
            account = "a" * account_length
            one_byte = helper._build_store_command(account, b"x")
            overhead = len(one_byte) - 2
            if (helper.SECURITY_INPUT_LIMIT - overhead) % 2 == 0:
                break
        else:
            raise AssertionError("could not construct exact parser-boundary case")

        exact_secret_length = (helper.SECURITY_INPUT_LIMIT - overhead) // 2
        accepted = b"x" * (exact_secret_length - 1)
        rejected = b"x" * exact_secret_length
        accepted_command = helper._build_store_command(account, accepted)
        require(len(accepted_command) < helper.SECURITY_INPUT_LIMIT, "accepted command crossed parser bound")
        require(helper.store_password(account, accepted, runner=fake_runner) is True, "bounded command rejected")
        calls.clear()
        require(
            helper.store_password(account, rejected, runner=fake_runner) is False,
            "4,096-byte command must fail closed",
        )
        require(calls == [], "oversized command must fail before security execution")
        require(helper.store_password(account, b"", runner=fake_runner) is False, "empty secret must fail closed")
        require(calls == [], "empty secret must fail before security execution")

    check("keychain command rejects injection and 4096-byte parser boundary", test_keychain_command_rejects_injection_and_parser_overflow)

    def test_keychain_failure_is_stable_and_redacted():
        helper = load_keychain_helper()
        secret = b"synthetic-sensitive-value"

        def failing_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 73, stdout=b"raw failure", stderr=secret)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            ok = helper.store_password("account", secret, runner=failing_runner)
        require(ok is False, "nonzero security status must fail")
        require(stdout.getvalue() == "" and stderr.getvalue() == "", "security failure leaked output")

        def raising_runner(argv, **kwargs):
            raise OSError(f"launch failed with {secret!r}")

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            ok = helper.store_password("account", secret, runner=raising_runner)
        require(ok is False, "security launch failure must fail")
        require(stdout.getvalue() == "" and stderr.getvalue() == "", "launch failure leaked output")

    check("keychain failures are stable and redacted", test_keychain_failure_is_stable_and_redacted)

    def test_profile_store_stages_and_never_rebinds_an_existing_record():
        helper = load_keychain_helper()
        require(hasattr(helper, "store_profile"), "profile transaction helper is missing")
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            original = {"other": {"connection_string": "postgresql://u@old.invalid/db"}}
            profiles_path.write_text(json.dumps(original))
            calls = []

            def successful_runner(argv, **kwargs):
                calls.append((argv, kwargs))
                live = json.loads(profiles_path.read_text())
                require("new" not in live, "new profile became usable before Keychain success")
                staged = [
                    item
                    for item in profiles_path.parent.glob(".profiles.json.*")
                    if item.name != ".profiles.json.lock"
                ]
                require(len(staged) == 1, f"expected one same-directory staged file: {staged}")
                staged_data = json.loads(staged[0].read_text())
                require(staged_data["new"]["connection_string"].endswith("new.invalid/db"), staged_data)
                return subprocess.CompletedProcess(argv, 0)

            status = helper.store_profile(
                "new",
                b"synthetic",
                profiles_path,
                "postgresql://u:****@new.invalid/db",
                runner=successful_runner,
            )
            require(status == helper.PROFILE_STORE_OK, f"profile transaction failed: {status}")
            require(json.loads(profiles_path.read_text())["new"]["connection_string"].endswith("new.invalid/db"), "staged profile was not published")

            before = profiles_path.read_bytes()
            calls.clear()
            status = helper.store_profile(
                "new",
                b"replacement",
                profiles_path,
                "postgresql://u:****@different.invalid/db",
                runner=successful_runner,
            )
            require(status == helper.PROFILE_EXISTS, f"existing profile was not rejected: {status}")
            require(calls == [], "Keychain ran before existing-profile rejection")
            require(profiles_path.read_bytes() == before, "existing profile changed on rejected replacement")

            profiles_path.write_text("{malformed")
            status = helper.store_profile(
                "another",
                b"synthetic",
                profiles_path,
                "postgresql://u:****@another.invalid/db",
                runner=successful_runner,
            )
            require(status == helper.PROFILE_STATE_FAILURE, f"malformed profiles JSON was accepted: {status}")
            require(calls == [], "Keychain ran before malformed profiles rejection")
            require(profiles_path.read_text() == "{malformed", "malformed profiles file was overwritten")

    check(
        "profile transaction stages first and rejects unsafe replacement",
        test_profile_store_stages_and_never_rebinds_an_existing_record,
    )

    def test_profile_publish_failure_leaves_only_an_orphan_credential():
        helper = load_keychain_helper()
        require(hasattr(helper, "store_profile"), "profile transaction helper is missing")
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            profiles_path.write_text(json.dumps({"other": {"connection_string": "postgresql://u@old.invalid/db"}}))

            def successful_runner(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0)

            def failing_replace(source, destination):
                raise OSError("synthetic publish failure")

            status = helper.store_profile(
                "new",
                b"synthetic",
                profiles_path,
                "postgresql://u:****@new.invalid/db",
                runner=successful_runner,
                replacer=failing_replace,
            )
            require(status == helper.PROFILE_STATE_FAILURE, f"publish failure was not reported: {status}")
            live = json.loads(profiles_path.read_text())
            require("new" not in live, "publish failure left a usable mismatched profile")
            staged = [
                item
                for item in profiles_path.parent.glob(".profiles.json.*")
                if item.name != ".profiles.json.lock"
            ]
            require(staged == [], "staged profile was not cleaned")

    check(
        "profile publish failure leaves no usable mismatched record",
        test_profile_publish_failure_leaves_only_an_orphan_credential,
    )

    def test_profile_mutations_are_serialized_without_lost_updates():
        helper = load_keychain_helper()
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            profiles_path.write_text(
                json.dumps({"baseline": {"connection_string": "postgresql://u@base.invalid/db"}})
            )
            entered = threading.Event()
            release = threading.Event()
            first_status = []

            def blocking_runner(argv, **kwargs):
                entered.set()
                require(release.wait(3), "concurrency harness did not release the first writer")
                return subprocess.CompletedProcess(argv, 0)

            def first_writer():
                first_status.append(
                    helper.store_profile(
                        "first",
                        b"first-secret",
                        profiles_path,
                        "postgresql://u:****@first.invalid/db",
                        runner=blocking_runner,
                    )
                )

            thread = threading.Thread(target=first_writer)
            thread.start()
            require(entered.wait(3), "first profile writer never entered Keychain storage")

            second_calls = []

            def second_runner(argv, **kwargs):
                second_calls.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 0)

            second_status = helper.store_profile(
                "second",
                b"second-secret",
                profiles_path,
                "postgresql://u:****@second.invalid/db",
                runner=second_runner,
            )
            remove_status = helper.remove_profile(
                "baseline",
                profiles_path,
                runner=second_runner,
            )
            require(second_status == helper.PROFILE_BUSY, f"concurrent add was not bounded: {second_status}")
            require(remove_status == helper.PROFILE_BUSY, f"concurrent remove was not bounded: {remove_status}")
            require(second_calls == [], "contending mutation reached Keychain")

            release.set()
            thread.join(3)
            require(not thread.is_alive(), "first profile writer did not terminate")
            require(first_status == [helper.PROFILE_STORE_OK], f"first writer failed: {first_status}")
            live = json.loads(profiles_path.read_text())
            require(set(live) == {"baseline", "first"}, f"contending mutation changed state: {live}")
            require(live["first"]["credential_required"] is True, "credential marker was not published")

            retry_status = helper.store_profile(
                "second",
                b"second-secret",
                profiles_path,
                "postgresql://u:****@second.invalid/db",
                runner=second_runner,
            )
            require(retry_status == helper.PROFILE_STORE_OK, f"later distinct add failed: {retry_status}")
            require(set(json.loads(profiles_path.read_text())) == {"baseline", "first", "second"}, "later add lost a record")

            same_name_status = helper.store_profile(
                "first",
                b"replacement",
                profiles_path,
                "postgresql://u:****@other.invalid/db",
                runner=second_runner,
            )
            require(same_name_status == helper.PROFILE_EXISTS, f"published same-name add was accepted: {same_name_status}")

    check(
        "profile add/remove mutations share one bounded lock",
        test_profile_mutations_are_serialized_without_lost_updates,
    )

    def test_passwordless_profile_cannot_consume_a_publish_failure_orphan():
        helper = load_keychain_helper()
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "agent-home" / "psql" / "profiles.json"
            keychain = {}

            def keychain_runner(argv, **kwargs):
                command = kwargs.get("input", b"")
                if command:
                    keychain["orphan"] = b"old-secret"
                return subprocess.CompletedProcess(argv, 0)

            def failing_replace(source, destination):
                raise OSError("synthetic publish failure")

            first = helper.store_profile(
                "orphan",
                b"old-secret",
                profiles_path,
                "postgresql://u:****@old.invalid/db",
                runner=keychain_runner,
                replacer=failing_replace,
            )
            require(first == helper.PROFILE_STATE_FAILURE, f"publish failure was not retained: {first}")
            require(keychain.get("orphan") == b"old-secret", "orphan setup did not store a credential")

            second = helper.store_profile(
                "orphan",
                b"",
                profiles_path,
                "postgresql://u@new.invalid/db",
                runner=keychain_runner,
                store_credential=False,
            )
            require(second == helper.PROFILE_STORE_OK, f"safe passwordless add failed: {second}")
            profile = helper.read_profile("orphan", profiles_path)
            require(profile == ("postgresql://u@new.invalid/db", False), f"unsafe profile metadata: {profile}")

            marker = Path(tmpdir) / "keychain-read"
            password_seen = Path(tmpdir) / "password-seen"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
ensure_psql() {{ :; }}
_read_password_into() {{ : > "{marker}"; printf -v "$1" '%s' 'old-secret'; }}
run_psql_raw() {{
    if [[ -n "$_PG_PASSWORD" ]]; then : > "{password_seen}"; fi
    printf '%s' 'PostgreSQL 16.0'
}}
save_session() {{ :; }}
snapshot_begin() {{ :; }}
snapshot_field() {{ :; }}
snapshot_end() {{ :; }}
cmd_connect --profile orphan >/dev/null
'''
            result = run_bash(script)
            require(result.returncode == 0, f"passwordless profile connect failed: {result.stderr}")
            require(not marker.exists(), "passwordless profile read a stale Keychain credential")
            require(not password_seen.exists(), "passwordless profile sent a stale credential")

    check(
        "passwordless profiles cannot consume orphaned credentials",
        test_passwordless_profile_cannot_consume_a_publish_failure_orphan,
    )

    def test_profile_metadata_rejects_ambiguous_credential_state():
        helper = load_keychain_helper()
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            invalid_records = [
                {"connection_string": "postgresql://u:****@db.invalid/d", "credential_required": False},
                {"connection_string": "postgresql://u@db.invalid/d", "credential_required": True},
                {"connection_string": "postgresql://u@db.invalid/d", "credential_required": 1},
                {"connection_string": "postgresql://u@db.invalid/d", "credential_required": None},
                {"connection_string": "postgresql://u:raw@db.invalid/d", "credential_required": False},
                {"connection_string": "postgresql://u@db.invalid/d?password=raw"},
                {"connection_string": "postgresql://u@db.invalid/d?SSL%70ASSWORD=raw"},
                {"connection_string": "host=db.invalid dbname=d user=u password=raw"},
                {"connection_string": "postgresql://user:synthetic-secret/db"},
            ]
            for record in invalid_records:
                profiles_path.write_text(json.dumps({"bad": record}))
                try:
                    helper.read_profile("bad", profiles_path)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"ambiguous credential record was accepted: {record}")

            profiles_path.write_text(
                json.dumps(
                    {
                        "oversized": {
                            "connection_string": "postgresql://u@host/d?x="
                            + "a" * helper.PROFILE_INPUT_LIMIT,
                            "credential_required": False,
                        }
                    }
                )
            )
            try:
                helper.read_profile("oversized", profiles_path)
            except ValueError:
                pass
            else:
                raise AssertionError("oversized legacy profile was accepted")

            profiles_path.write_text(
                json.dumps(
                    {
                        "legacy-keychain": {"connection_string": "postgresql://u:****@db.invalid/d"},
                        "legacy-passwordless": {"connection_string": "postgresql://u@db.invalid/d"},
                        "legacy-empty-password": {"connection_string": "postgresql://u:@db.invalid/d"},
                    }
                )
            )
            require(helper.read_profile("legacy-keychain", profiles_path)[1] is True, "legacy masked profile lost compatibility")
            require(helper.read_profile("legacy-passwordless", profiles_path)[1] is False, "legacy passwordless profile became credentialed")
            require(helper.read_profile("legacy-empty-password", profiles_path)[1] is False, "legacy empty-password profile became credentialed")

            profiles_path.write_text(
                '{"dup":{"connection_string":"postgresql://u@safe.invalid/d",'
                '"connection_string":"postgresql://u:raw@unsafe.invalid/d"}}'
            )
            try:
                helper.read_profile("dup", profiles_path)
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate profile-state key was accepted")

    check(
        "profile metadata rejects ambiguous credential binding",
        test_profile_metadata_rejects_ambiguous_credential_state,
    )

    def test_profile_names_cannot_collide_with_session_credentials():
        helper = load_keychain_helper()
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            profiles_path.write_text(json.dumps({}))
            calls = []

            def fake_runner(argv, **kwargs):
                calls.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 0)

            reserved = "session-db.invalid-5432-user-database"
            add_status = helper.store_profile(
                reserved,
                b"synthetic",
                profiles_path,
                "postgresql://u:****@db.invalid/d",
                runner=fake_runner,
            )
            remove_status = helper.remove_profile(reserved, profiles_path, runner=fake_runner)
            require(add_status == helper.PROFILE_STATE_FAILURE, f"reserved profile add passed: {add_status}")
            require(remove_status == helper.PROFILE_STATE_FAILURE, f"reserved profile remove passed: {remove_status}")
            require(calls == [], "reserved profile name reached Keychain")
            require(json.loads(profiles_path.read_text()) == {}, "reserved profile changed state")

            profiles_path.write_text(
                json.dumps({reserved: {"connection_string": "postgresql://u@db.invalid/d"}})
            )
            try:
                helper.read_profile(reserved, profiles_path)
            except ValueError:
                pass
            else:
                raise AssertionError("reserved legacy profile could access a session credential")

    check(
        "profile names cannot collide with the session credential namespace",
        test_profile_names_cannot_collide_with_session_credentials,
    )

    def test_profile_removal_only_deletes_explicitly_bound_credentials():
        helper = load_keychain_helper()
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = Path(tmpdir) / "profiles.json"
            profiles_path.write_text(
                json.dumps(
                    {
                        "plain": {
                            "connection_string": "postgresql://u@plain.invalid/d",
                            "credential_required": False,
                        },
                        "secret": {
                            "connection_string": "postgresql://u:****@secret.invalid/d",
                            "credential_required": True,
                        },
                    }
                )
            )
            calls = []

            def fake_runner(argv, **kwargs):
                calls.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 0)

            plain_status = helper.remove_profile("plain", profiles_path, runner=fake_runner)
            require(plain_status == helper.PROFILE_STORE_OK, f"passwordless remove failed: {plain_status}")
            require(calls == [], "passwordless profile removal reached Keychain")

            missing_status = helper.remove_profile("missing", profiles_path, runner=fake_runner)
            require(missing_status == helper.PROFILE_NOT_FOUND, f"missing remove drifted: {missing_status}")
            require(calls == [], "missing profile removal reached Keychain")

            secret_status = helper.remove_profile("secret", profiles_path, runner=fake_runner)
            require(secret_status == helper.PROFILE_STORE_OK, f"credentialed remove failed: {secret_status}")
            require(len(calls) == 1, f"credentialed removal did not make one cleanup call: {calls}")
            argv, kwargs = calls[0]
            require(argv[:2] == ["/usr/bin/security", "delete-generic-password"], f"unsafe delete argv: {argv}")
            require(kwargs.get("timeout") == helper.SECURITY_TIMEOUT_SECONDS, "Keychain delete was unbounded")
            require("PGPASSWORD" not in kwargs.get("env", {}), "Keychain delete inherited PGPASSWORD")

    check(
        "profile removal only deletes explicitly bound credentials",
        test_profile_removal_only_deletes_explicitly_bound_credentials,
    )

    def test_bash_keychain_reads_preserve_terminal_lfs_and_scrub_children():
        with tempfile.TemporaryDirectory() as tmpdir:
            direct_bytes = Path(tmpdir) / "direct-bytes"
            session_bytes = Path(tmpdir) / "session-bytes"
            profile_bytes = Path(tmpdir) / "profile-bytes"
            env_leak = Path(tmpdir) / "env-leak"
            agent_home = Path(tmpdir) / "agent-home"
            profiles_path = agent_home / "psql" / "profiles.json"
            profiles_path.parent.mkdir(parents=True)
            profiles_path.write_text(
                json.dumps(
                    {
                        "with-secret": {
                            "connection_string": "postgresql://u:****@db.invalid/d",
                            "credential_required": True,
                        }
                    }
                )
            )
            session_path = agent_home / "psql" / "session.json"
            session_path.write_text(
                json.dumps(
                    {
                        "host": "db.invalid",
                        "port": "5432",
                        "database": "d",
                        "user": "u",
                        "sslmode": "require",
                    }
                )
            )
            script = f'''
export AGENT_DO_HOME="{agent_home}"
source "{TOOL}" help >/dev/null
_actual_macos() {{
    if [[ -n "${{PGPASSWORD+x}}" ]]; then : > "{env_leak}"; fi
    return 0
}}
_run_keychain_helper() {{
    if [[ -n "${{PGPASSWORD+x}}" ]]; then : > "{env_leak}"; fi
    if [[ "$1" == "--read" ]]; then
        builtin printf 'abc\037\n\n'
    else
        command python3 "${{SCRIPT_DIR}}/../lib/psql_keychain_store.py" "$@"
    fi
}}

export PGPASSWORD='ambient-secret'
stored_pw=''
_read_password_into stored_pw direct || exit 71
builtin printf '%s' "$stored_pw" > "{direct_bytes}"

unset PGPASSWORD
load_session || exit 72
builtin printf '%s' "$_PG_PASSWORD" > "{session_bytes}"

ensure_psql() {{ :; }}
run_psql_raw() {{ builtin printf '%s' "$_PG_PASSWORD" > "{profile_bytes}"; printf '%s' 'PostgreSQL 16.0'; }}
_store_session_password() {{ :; }}
save_session() {{ :; }}
snapshot_begin() {{ :; }}
snapshot_field() {{ :; }}
snapshot_end() {{ :; }}
cmd_connect --profile with-secret >/dev/null || exit 73
'''
            result = run_bash(script)
            require(
                result.returncode == 0,
                f"framed read harness failed rc={result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            expected = b"abc\x1f\n\n"
            require(direct_bytes.read_bytes() == expected, "direct Keychain read stripped terminal bytes")
            require(session_bytes.read_bytes() == expected, "session Keychain read stripped terminal bytes")
            require(profile_bytes.read_bytes() == expected, "profile Keychain read stripped terminal bytes")
            require(not env_leak.exists(), "ambient PGPASSWORD reached a Keychain read child")

    check(
        "Keychain read bridge preserves terminal LFs and scrubs child environments",
        test_bash_keychain_reads_preserve_terminal_lfs_and_scrub_children,
    )

    def test_connect_keychain_failure_does_not_save_session():
        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "session-written"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
ensure_psql() {{ :; }}
run_psql_raw() {{ printf '%s' 'PostgreSQL 16.0'; }}
_store_session_password() {{ return 73; }}
save_session() {{ : > "{marker}"; }}
export PGHOST=db.invalid PGPORT=5432 PGDATABASE=db PGUSER=user PGPASSWORD=synthetic PGSSLMODE=require
if cmd_connect; then
    printf 'unexpected-success'
    exit 90
else
    printf 'status=%s' "$?"
fi
'''
            r = run_bash(script)
            require(r.returncode == 0, f"connect failure harness failed: {r.stderr}")
            require(
                r.stdout
                == '{"ok": false, "error": "Failed to store password in macOS Keychain"}\nstatus=1',
                f"connect failure must be stable, generic JSON: {r.stdout!r}",
            )
            require(not marker.exists(), "session was written before Keychain storage succeeded")

    check("connect does not write a false session on keychain failure", test_connect_keychain_failure_does_not_save_session)

    def test_connect_user_fallback_does_not_fork_before_secret_scrub():
        with tempfile.TemporaryDirectory() as tmpdir:
            whoami_marker = Path(tmpdir) / "whoami-called"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
ensure_psql() {{ :; }}
run_psql_raw() {{ printf '%s' 'PostgreSQL 16.0'; }}
whoami() {{ : > "{whoami_marker}"; printf 'wrong-user'; }}
_store_session_password() {{ return 1; }}
export PGHOST=db.invalid PGPORT=5432 PGDATABASE=db PGPASSWORD=synthetic PGSSLMODE=require
unset PGUSER
USER=expected-user
if cmd_connect; then exit 90; fi
'''
            r = run_bash(script)
            require(r.returncode == 0, f"connect fallback harness failed: {r.stderr}")
            require(not whoami_marker.exists(), "connect forked whoami while PGPASSWORD was exported")

    check(
        "connect user fallback is in-shell before secret scrub",
        test_connect_user_fallback_does_not_fork_before_secret_scrub,
    )

    def test_connect_does_not_rebuild_a_secret_uri_for_masking():
        with tempfile.TemporaryDirectory() as tmpdir:
            leak_marker = Path(tmpdir) / "mask-received-secret"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
ensure_psql() {{ :; }}
run_psql_raw() {{ printf '%s' 'PostgreSQL 16.0'; }}
_store_session_password() {{ [[ "$1" == "$PGPASSWORD" ]]; }}
save_session() {{ :; }}
snapshot_begin() {{ :; }}
snapshot_field() {{ :; }}
snapshot_end() {{ :; }}
mask_connection_string() {{
    if [[ "$1" == *"$PGPASSWORD"* ]]; then
        : > "{leak_marker}"
        return 73
    fi
    printf '%s' "$1"
}}
export PGHOST=db.invalid PGPORT=5432 PGDATABASE=db PGUSER=user
export PGPASSWORD='synthetic-post-store-secret' PGSSLMODE=require
cmd_connect
'''
            r = run_bash(script)
            require(r.returncode == 0, f"connect success harness failed: {r.stderr}")
            require(not leak_marker.exists(), "connect passed a rebuilt secret URI to the masking child")
            require("synthetic-post-store-secret" not in r.stdout, "connect output exposed the secret")
            data = json.loads(r.stdout)
            require(data["ok"] is True, f"connect harness did not succeed: {data}")
            require(data["masked_uri"] == "postgresql://user:****@db.invalid:5432/db", data)

    check(
        "connect never rebuilds a secret URI for post-store masking",
        test_connect_does_not_rebuild_a_secret_uri_for_masking,
    )

    def test_profile_keychain_failure_does_not_write_profile():
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "agent-home" / "psql" / "profiles.json"
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
_run_keychain_helper() {{ return 1; }}
if cmd_profile_add testdb 'postgresql://user:synthetic@db.invalid:5432/db'; then
    printf 'unexpected-success'
    exit 90
else
    printf 'status=%s' "$?"
fi
'''
            r = run_bash(script)
            require(r.returncode == 0, f"profile failure harness failed: {r.stderr}")
            require(
                r.stdout
                == '{"ok": false, "error": "Failed to store password in macOS Keychain"}\nstatus=1',
                f"profile failure must be stable, generic JSON: {r.stdout!r}",
            )
            require(not profiles_file.exists(), "profile was written before Keychain storage succeeded")

    check("profile add does not write a false record on keychain failure", test_profile_keychain_failure_does_not_write_profile)

    def test_profile_replacement_requires_remove_first():
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "agent-home" / "psql" / "profiles.json"
            profiles_file.parent.mkdir(parents=True)
            original = {"testdb": {"connection_string": "postgresql://user:****@old.invalid/db"}}
            profiles_file.write_text(json.dumps(original))
            script = f'''
export AGENT_DO_HOME="{tmpdir}/agent-home"
source "{TOOL}" help >/dev/null
_run_keychain_helper() {{ return 3; }}
if cmd_profile_add testdb 'postgresql://user:synthetic@new.invalid/db'; then
    exit 90
else
    printf 'status=%s' "$?"
fi
'''
            r = run_bash(script)
            require(r.returncode == 0, f"profile replacement harness failed: {r.stderr}")
            require(
                r.stdout
                == '{"ok": false, "error": "Profile \'testdb\' already exists. Remove it before replacing it."}\nstatus=1',
                f"profile replacement error was not actionable: {r.stdout!r}",
            )
            require(json.loads(profiles_file.read_text()) == original, "rejected replacement changed live profile")

    check("profile replacement requires removal first", test_profile_replacement_requires_remove_first)

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

    # ---- Query fidelity: errors, NULLs, blank rows, truncation (fake binaries) ----
    FAKE_PSQL = r"""#!/usr/bin/env python3
import re, sys
args = sys.argv[1:]
null = ""
sql = None
sql_file = None
for i, a in enumerate(args):
    if a == "-P" and args[i + 1].startswith("null="):
        null = args[i + 1][len("null="):]
    if a == "-c":
        sql = args[i + 1]
    if a == "-f":
        sql_file = args[i + 1]
if sql_file is not None:
    body = open(sql_file).read()
    if "RAISE" in body:
        sys.stderr.write("psql:" + sql_file + ":3: ERROR:  guard refused\n")
        sys.exit(3)
    print("DO")
    sys.exit(0)
if "no_such_col" in sql:
    sys.stderr.write('ERROR:  column "no_such_col" does not exist\nLINE 1: select no_such_col\n')
    sys.exit(1)
if "null_vs_empty" in sql:
    sys.stdout.write("a,b,c\n" + null + ",,x\n")
elif "all_null" in sql:
    sys.stdout.write("x\n" + (null + "\n") * 3)
elif "empty_text" in sql:
    sys.stdout.write("e\n" + "\n" * 3)
elif "multiline" in sql:
    sys.stdout.write('m,n\n"line one\nline two",' + null + '\n')
elif "series" in sql:
    m = re.search(r"LIMIT (\d+)\s*$", sql)
    total = int(re.search(r"series_(\d+)", sql).group(1))
    n = min(total, int(m.group(1))) if m else total
    sys.stdout.write("g\n" + "".join(f"{i}\n" for i in range(1, n + 1)))
else:
    sys.stdout.write("?column?\n1\n")
"""
    FAKE_FAIL = "#!/bin/sh\necho \"$(basename \"$0\"): error: connection to server failed\" >&2\nexit 1\n"

    def fake_env(tmpdir: str) -> dict:
        bin_dir = Path(tmpdir) / "fakebin"
        bin_dir.mkdir()
        for name, body in (("psql", FAKE_PSQL), ("pg_dump", FAKE_FAIL), ("pg_restore", FAKE_FAIL)):
            exe = bin_dir / name
            exe.write_text(body)
            exe.chmod(0o755)
        session = Path(tmpdir) / ".agent-do" / "psql" / "session.json"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text(json.dumps({"host": "fake.invalid", "port": "5432", "database": "fakedb",
                                       "user": "u", "sslmode": "prefer"}))
        return {"HOME": tmpdir, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PGPASSWORD": "x"}

    def last_json(stdout: str) -> dict:
        dec = json.JSONDecoder()
        i, out = 0, None
        while i < len(stdout):
            while i < len(stdout) and stdout[i].isspace():
                i += 1
            if i >= len(stdout):
                break
            out, i = dec.raw_decode(stdout, i)
        require(isinstance(out, dict), f"no JSON result object: {stdout!r}")
        return out

    def test_query_error_surfaces():
        with tempfile.TemporaryDirectory() as tmpdir:
            r = run_tool("query", "select no_such_col from t", env_override=fake_env(tmpdir))
            require(r.returncode == 4, f"query error exit should be 4 (documented 'Query error'), got {r.returncode}")
            data = last_json(r.stdout)
            require(data.get("ok") is False, f"query error not reported: {data}")
            require("no_such_col" in data.get("error", ""), f"psql's message missing: {data}")

    check("query: SQL error returns ok:false with psql's message, exit 4", test_query_error_surfaces)

    def test_query_null_vs_empty():
        with tempfile.TemporaryDirectory() as tmpdir:
            data = last_json(run_tool("query", "select null_vs_empty", env_override=fake_env(tmpdir)).stdout)
            require(data["rows"] == [[None, "", "x"]], f"NULL and empty text not distinguished: {data}")

    check("query: NULL is JSON null, empty text stays empty", test_query_null_vs_empty)

    def test_query_all_null_rows_counted():
        with tempfile.TemporaryDirectory() as tmpdir:
            data = last_json(run_tool("query", "select all_null", env_override=fake_env(tmpdir)).stdout)
            require(data["row_count"] == 3 and data["rows"] == [[None]] * 3, f"all-NULL rows dropped: {data}")

    check("query: all-NULL rows are kept and counted", test_query_all_null_rows_counted)

    def test_query_trailing_empty_text_rows_kept():
        with tempfile.TemporaryDirectory() as tmpdir:
            data = last_json(run_tool("query", "select empty_text", env_override=fake_env(tmpdir)).stdout)
            require(data["row_count"] == 3 and data["rows"] == [[""]] * 3, f"blank rows dropped: {data}")

    check("query: trailing single-column empty-text rows are kept", test_query_trailing_empty_text_rows_kept)

    def test_query_multiline_value_is_one_cell():
        with tempfile.TemporaryDirectory() as tmpdir:
            data = last_json(run_tool("query", "select multiline", env_override=fake_env(tmpdir)).stdout)
            require(data.get("rows") == [["line one\nline two", None]] and data.get("row_count") == 1,
                    f"quoted multi-line value split or mis-parsed: {data}")

    check("query: a quoted multi-line value stays one cell", test_query_multiline_value_is_one_cell)

    def test_query_truncation_reported():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = fake_env(tmpdir)
            cut = last_json(run_tool("query", "select series_300", env_override=env).stdout)
            require(cut.get("row_count") == 200 and cut.get("truncated") is True and cut.get("limit") == 200,
                    f"default limit cut rows silently: {cut}")
            exact = last_json(run_tool("query", "select series_200", env_override=env).stdout)
            require(exact.get("row_count") == 200 and exact.get("truncated") is False,
                    f"exactly-the-limit result wrongly marked truncated: {exact}")
            own = last_json(run_tool("query", "select series_300", "--limit", "5", env_override=env).stdout)
            require(own.get("row_count") == 5 and own.get("truncated") is True and own.get("limit") == 5,
                    f"--limit truncation not reported: {own}")

    check("query: a cut result reports truncated and the limit", test_query_truncation_reported)

    def test_exec_error_surfaces():
        with tempfile.TemporaryDirectory() as tmpdir:
            sql = Path(tmpdir) / "guard.sql"
            sql.write_text("DO $$ BEGIN\n  RAISE EXCEPTION 'guard refused';\nEND $$;\n")
            r = run_tool("exec", str(sql), env_override=fake_env(tmpdir))
            require(r.returncode == 4, f"exec error exit should be 4, got {r.returncode}")
            data = last_json(r.stdout)
            require(data.get("ok") is False and "guard refused" in data.get("error", ""), f"exec error not reported: {data}")

    check("exec: SQL error returns ok:false with psql's message, exit 4", test_exec_error_surfaces)

    def test_dump_and_restore_errors_surface():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = fake_env(tmpdir)
            r = run_tool("dump", str(Path(tmpdir) / "out.sql"), env_override=env)
            require(r.returncode == 7, f"dump error exit should be 7, got {r.returncode}")
            require("connection to server failed" in last_json(r.stdout).get("error", ""), f"dump error missing: {r.stdout}")
            dumpfile = Path(tmpdir) / "in.dump"
            dumpfile.write_bytes(b"PGDMP")
            r = run_tool("restore", str(dumpfile), env_override=env)
            require(r.returncode == 7, f"restore error exit should be 7, got {r.returncode}")
            require("connection to server failed" in last_json(r.stdout).get("error", ""), f"restore error missing: {r.stdout}")

    check("dump/restore: failures return ok:false with the tool's message, exit 7", test_dump_and_restore_errors_surface)

    # ---- One JSON document per call (no separate request header) ----
    def single_doc(stdout: str) -> dict:
        try:
            data = json.loads(stdout)
        except ValueError as exc:
            raise AssertionError(f"stdout is not exactly one JSON document ({exc}): {stdout!r}")
        require(isinstance(data, dict), f"expected one JSON object: {stdout!r}")
        return data

    def test_query_is_one_document():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = fake_env(tmpdir)
            ok = single_doc(run_tool("query", "select null_vs_empty", env_override=env).stdout)
            require(ok.get("ok") is True and ok.get("database") == "fakedb" and ok.get("sql") == "select null_vs_empty",
                    f"query result must name the database and the SQL as given: {ok}")
            err = single_doc(run_tool("query", "select no_such_col from t", env_override=env).stdout)
            require(err.get("ok") is False and err.get("database") == "fakedb" and err.get("sql") == "select no_such_col from t",
                    f"query error must name the database and the SQL as given: {err}")

    check("query: stdout is one JSON document naming database and sql", test_query_is_one_document)

    def test_exec_is_one_document():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = fake_env(tmpdir)
            good = Path(tmpdir) / "good.sql"
            good.write_text("select 1;\n")
            bad = Path(tmpdir) / "bad.sql"
            bad.write_text("DO $$ BEGIN RAISE EXCEPTION 'x'; END $$;\n")
            for f, expect_ok in ((good, True), (bad, False)):
                data = single_doc(run_tool("exec", str(f), env_override=env).stdout)
                require(data.get("ok") is expect_ok and data.get("database") == "fakedb" and data.get("file") == str(f),
                        f"exec result must name the database and file: {data}")

    check("exec: stdout is one JSON document naming database and file", test_exec_is_one_document)

    def test_connect_is_one_document():
        with tempfile.TemporaryDirectory() as tmpdir:
            env = fake_env(tmpdir)
            r = run_tool("connect", "postgresql://u@fake.invalid:5432/conndb", env_override=env)
            data = single_doc(r.stdout)
            require(data.get("ok") is True and data.get("database") == "conndb", f"connect result: {data}")

    check("connect: stdout is one JSON document", test_connect_is_one_document)

    # ---- Summary ----
    print(f"\npsql tests: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
