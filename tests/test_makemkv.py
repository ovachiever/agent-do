#!/usr/bin/env python3
"""Tests for agent-makemkv — MakeMKV (makemkvcon) rip CLI wrapper.

Covers: help, disc normalization, robot-output parsing (drives/info/version),
minlength title filtering, rip→verify flow, dry-run, JSON output, and the
missing-binary error path. Uses a mock makemkvcon so no optical drive is needed.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-makemkv"

# A mock makemkvcon that emits realistic robot-mode output. For rip/backup it
# writes a fake artifact into the output directory (the last argument).
# DRV:1,0,... is AP_DriveStateEmptyClosed — a present empty drive, not a missing one.
MOCK = r"""#!/usr/bin/env bash
mode=""
for a in "$@"; do
  case "$a" in
    disc:9999) mode=drives ;;
    info) [[ -z "$mode" ]] && mode=info ;;
    mkv) mode=rip ;;
    backup) mode=backup ;;
  esac
done
echo 'MSG:1005,0,1,"MakeMKV v1.17.7 linux(x64-release) started","%1 started","MakeMKV v1.17.7 linux(x64-release)"'
echo 'MSG:5011,0,0,"The program has been registered.","",""'
case "$mode" in
  drives)
    echo 'DRV:0,2,999,12,"BD-RE PIONEER BD-RW BDR-209M","MY_MOVIE_DISC","/dev/rdisk2"'
    echo 'DRV:1,0,999,0,"BD-RE HL-DT-ST BD-RE BH16NS40","","/dev/rdisk3"'
    echo 'DRV:2,256,999,0,"","",""'
    echo 'TCOUNT:0'
    ;;
  info)
    echo 'CINFO:2,0,"MY_MOVIE_DISC"'
    echo 'CINFO:32,0,"MY_MOVIE_DISC"'
    echo 'TCOUNT:2'
    echo 'TINFO:0,2,0,"MY_MOVIE_DISC"'
    echo 'TINFO:0,8,0,"12"'
    echo 'TINFO:0,9,0,"1:52:30"'
    echo 'TINFO:0,10,0,"24.7 GB"'
    echo 'TINFO:0,11,0,"26494840832"'
    echo 'TINFO:0,27,0,"title_t00.mkv"'
    echo 'TINFO:1,8,0,"1"'
    echo 'TINFO:1,9,0,"0:00:45"'
    echo 'TINFO:1,27,0,"title_t01.mkv"'
    ;;
  rip)
    echo 'MSG:5036,0,0,"Copy complete. 1 title(s) saved, 0 failed","",""'
    if [[ -n "${MOCK_MKV_EMPTY:-}" ]]; then
      exit 0
    fi
    out="${@: -1}"; head -c 1048576 /dev/zero > "$out/title_t00.mkv"
    ;;
  backup)
    echo 'MSG:5070,0,0,"Backup complete.","",""'
    out="${@: -1}"; mkdir -p "$out/BDMV"
    ;;
esac
exit 0
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


_MOCK_PATHS: list[str] = []
atexit.register(lambda: [os.unlink(p) for p in _MOCK_PATHS if os.path.exists(p)])


def make_mock() -> str:
    fd, path = tempfile.mkstemp(prefix="mock-makemkvcon-")
    with os.fdopen(fd, "w") as f:
        f.write(MOCK)
    os.chmod(path, 0o700)
    _MOCK_PATHS.append(path)
    return path


def run_tool(
    *args: str,
    bin_override: str | None = "MOCK",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if bin_override == "MOCK":
        env["AGENT_MAKEMKV_BIN"] = make_mock()
    elif bin_override is not None:
        env["AGENT_MAKEMKV_BIN"] = bin_override
    else:
        env.pop("AGENT_MAKEMKV_BIN", None)
    env.pop("MOCK_MKV_EMPTY", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(TOOL), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
        timeout=30,
    )


def main() -> int:
    failures = 0

    def check(name: str, fn) -> None:
        nonlocal failures
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ✗ {name}: {exc}")

    def test_help():
        r = run_tool("--help", bin_override=None)
        require(r.returncode == 0, "help should exit 0")
        require("agent-makemkv" in r.stdout, "help should name the tool")
        require("rip <disc>" in r.stdout, "help should document rip")

    check("--help lists commands", test_help)

    def test_unknown_command():
        r = run_tool("bogus", bin_override=None)
        require(r.returncode == 2, f"unknown command should exit 2, got {r.returncode}")

    check("unknown command exits 2", test_unknown_command)

    def test_drives_json():
        r = run_tool("drives", "--json")
        require(r.returncode == 0, f"drives should succeed: {r.stderr}")
        data = json.loads(r.stdout)
        drives = data["result"]["drives"]
        require(len(drives) == 2, f"loaded + empty-closed expected, got {drives}")
        by_index = {d["index"]: d for d in drives}
        require(by_index[0]["disc"] == "MY_MOVIE_DISC", f"disc label parsed: {by_index[0]}")
        require(by_index[0]["loaded"] is True, "drive 0 should report loaded")
        require(by_index[0]["state"] == 2, f"inserted state: {by_index[0]}")
        require(by_index[1]["loaded"] is False, "empty-closed tray is a present drive")
        require(by_index[1]["state"] == 0, f"empty_closed state: {by_index[1]}")
        require(by_index[1]["state_name"] == "empty_closed", f"state name: {by_index[1]}")

    check("drives keeps empty-closed trays and drops NoDrive slots", test_drives_json)

    def test_info_no_default_minlength():
        r = run_tool("info", "disc:0", "--json")
        require(r.returncode == 0, f"info should succeed: {r.stderr}")
        titles = json.loads(r.stdout)["result"]["titles"]
        require(len(titles) == 2, f"no --minlength must keep both titles, got {titles}")

    check("info without --minlength keeps short titles", test_info_no_default_minlength)

    def test_info_minlength_filters():
        r = run_tool("info", "disc:0", "--minlength", "120", "--json")
        require(r.returncode == 0, f"info should succeed: {r.stderr}")
        titles = json.loads(r.stdout)["result"]["titles"]
        require(len(titles) == 1, f"minlength should filter to 1 title, got {titles}")
        require(titles[0]["duration"] == "1:52:30", f"feature duration: {titles[0]}")
        require(titles[0]["chapters"] == "12", f"chapter count parsed: {titles[0]}")

    check("info --minlength filters short titles", test_info_minlength_filters)

    def test_info_minlength_override():
        r = run_tool("info", "0", "--minlength", "10", "--json")
        titles = json.loads(r.stdout)["result"]["titles"]
        require(len(titles) == 2, f"low minlength should keep both titles, got {titles}")

    check("info --minlength keeps short titles; bare index normalizes", test_info_minlength_override)

    def test_minlength_rejects_non_numeric():
        r = run_tool("info", "0", "--minlength", "nope", "--json")
        require(r.returncode == 2, f"bad --minlength should exit 2, got {r.returncode}")
        data = json.loads(r.stdout)
        require(data["success"] is False, f"should report failure: {data}")
        require("number" in data["error"], f"error should explain: {data}")

    check("--minlength rejects non-numeric values", test_minlength_rejects_non_numeric)

    def test_version():
        r = run_tool("version")
        require(r.returncode == 0, f"version should succeed: {r.stderr}")
        require("MakeMKV v1.17.7" in r.stdout, f"clean version expected: {r.stdout!r}")
        require("started" not in r.stdout, "version should strip the ' started' suffix")

    check("version reports clean banner", test_version)

    def test_snapshot_registration():
        r = run_tool("snapshot", "--json")
        require(r.returncode == 0, f"snapshot should succeed: {r.stderr}")
        snap = json.loads(r.stdout)["result"]
        require(snap["version"] == "MakeMKV v1.17.7 linux(x64-release)", f"version: {snap}")
        require(snap["registration"]["state"] == "registered", f"registration: {snap}")
        require(len(snap["drives"]) == 2, f"snapshot inherits empty-drive fix: {snap}")

    check("snapshot reports version, drives, and registration", test_snapshot_registration)

    def test_rip_then_verify():
        with tempfile.TemporaryDirectory() as outdir:
            r = run_tool("rip", "disc:0", "all", outdir)
            require(r.returncode == 0, f"rip should succeed: {r.stderr}")
            require((Path(outdir) / "title_t00.mkv").exists(), "rip should produce an mkv")
            require("title_t00.mkv" in r.stdout, f"rip should verify output: {r.stdout!r}")
            v = run_tool("verify", outdir, "--json", bin_override=None)
            data = json.loads(v.stdout)
            require(data["result"]["count"] == 1, f"verify should see 1 mkv: {data}")

    check("rip writes mkv and auto-verifies", test_rip_then_verify)

    def test_rip_json_is_one_document():
        with tempfile.TemporaryDirectory() as outdir:
            r = run_tool("rip", "disc:0", "all", outdir, "--json")
            require(r.returncode == 0, f"rip --json should succeed: {r.stderr}")
            require("MSG:" not in r.stdout, f"robot chatter leaked onto stdout: {r.stdout!r}")
            data = json.loads(r.stdout)
            require(data["success"] is True, f"envelope: {data}")
            require(data["result"]["count"] == 1, f"verify payload: {data}")
            require("MSG:" in r.stderr, f"chatter should land on stderr: {r.stderr!r}")

    check("rip --json is a single JSON document", test_rip_json_is_one_document)

    def test_rip_fails_when_nothing_written():
        with tempfile.TemporaryDirectory() as outdir:
            r = run_tool("rip", "disc:0", "all", outdir, "--json",
                         extra_env={"MOCK_MKV_EMPTY": "1"})
            require(r.returncode != 0, "rip with no output must fail")
            data = json.loads(r.stdout)
            require(data["success"] is False, f"should report failure: {data}")
            require("no .mkv" in data["error"], f"error should name the empty result: {data}")

    check("rip fails when makemkvcon exits 0 with no files", test_rip_fails_when_nothing_written)

    def test_missing_operands_exit_2():
        for args in (["rip"], ["rip", "disc:0"], ["rip", "disc:0", "all"],
                     ["backup"], ["backup", "disc:0"], ["verify"]):
            r = run_tool(*args, "--json")
            require(r.returncode == 2, f"{args} should exit 2, got {r.returncode}")
            data = json.loads(r.stdout)
            require(data["success"] is False and "required" in data["error"],
                    f"{args} should explain the missing operand: {data}")

    check("missing operands return structured exit-2 errors", test_missing_operands_exit_2)

    def test_dry_run():
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "rips"
            r = run_tool("rip", "disc:0", "all", str(outdir), "--dry-run")
            require(r.returncode == 0, "dry-run should exit 0")
            require("mkv disc:0 all" in r.stdout, f"dry-run should print command: {r.stdout!r}")
            require(not outdir.exists(), "dry-run must not create the output directory")

    check("--dry-run prints command without ripping", test_dry_run)

    def test_missing_binary():
        r = run_tool("drives", "--json", bin_override="/nonexistent/makemkvcon")
        require(r.returncode == 127, f"missing binary should exit 127, got {r.returncode}")
        data = json.loads(r.stdout)
        require(data["success"] is False, f"should report failure: {data}")
        require("not found" in data["error"], f"error should explain: {data}")

    check("missing binary errors with exit 127", test_missing_binary)

    def test_verify_no_binary_needed():
        with tempfile.TemporaryDirectory() as outdir:
            r = run_tool("verify", outdir, bin_override="/nonexistent")
            require(r.returncode == 0, "verify needs no binary")
            require("No .mkv" in r.stdout, f"empty verify message: {r.stdout!r}")

    check("verify works without makemkvcon", test_verify_no_binary_needed)

    print(f"\nmakemkv tests: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
