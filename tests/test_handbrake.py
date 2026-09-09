#!/usr/bin/env python3
"""Tests for the media family's handbrake provider — HandBrakeCLI MKV-to-MP4 transcode wrapper.

Covers: help, preset-list parsing, --json scan parsing, convert output naming
and auto-verify, batch skip/overwrite behavior, dry-run, JSON output, and the
missing-binary error path. Uses a mock HandBrakeCLI so no encoder is needed.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-media" / "providers" / "handbrake"

# A mock HandBrakeCLI that emits realistic output for --version,
# --preset-list, --scan --json, and encodes (writes a fake .mp4 to -o).
MOCK = r"""#!/usr/bin/env bash
mode=encode
out=""
prev=""
for a in "$@"; do
  case "$a" in
    --version) mode=version ;;
    --preset-list) mode=presets ;;
    --scan) mode=scan ;;
  esac
  [[ "$prev" == "-o" ]] && out="$a"
  prev="$a"
done
case "$mode" in
  version)
    echo "HandBrake 1.7.3"
    ;;
  presets)
    cat <<'EOF'
General/
    Very Fast 1080p30
        Small H.264 video (up to 1080p30) and AAC stereo audio, in an MP4 container.
    Fast 1080p30
        H.264 video (up to 1080p30) and AAC stereo audio, in an MP4 container.
    HQ 1080p30 Surround
        High quality H.264 video (up to 1080p30), AAC stereo audio, and Dolby Digital (AC-3) surround audio, in an MP4 container.
Web/
    Creator 1080p30
        High quality video for social media platforms.
EOF
    ;;
  scan)
    echo 'JSON Title Set: {'
    echo '  "MainFeature": 0,'
    echo '  "TitleList": ['
    echo '    {'
    echo '      "Index": 1, "Name": "My Movie",'
    echo '      "Duration": {"Hours": 1, "Minutes": 52, "Seconds": 30},'
    echo '      "Geometry": {"Width": 1920, "Height": 1080},'
    echo '      "VideoCodec": "h264",'
    echo '      "AudioList": [{"Language": "English", "CodecName": "dts"}],'
    echo '      "SubtitleList": [{"Language": "English"}, {"Language": "Spanish"}]'
    echo '    }'
    echo '  ]'
    echo '}'
    ;;
  encode)
    [[ -z "$out" ]] && exit 1
    if [[ -n "${MOCK_HB_FAIL:-}" ]]; then
      head -c 1024 /dev/zero > "$out"   # failed encode leaves partial output
      exit 1
    fi
    echo "Encoding: task 1 of 1, 100.00 %"
    head -c 524288 /dev/zero > "$out"
    ;;
esac
exit 0
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_mock() -> str:
    fd, path = tempfile.mkstemp(prefix="mock-handbrakecli-")
    with os.fdopen(fd, "w") as f:
        f.write(MOCK)
    os.chmod(path, 0o755)
    return path


def run_tool(
    *args: str,
    bin_override: str | None = "MOCK",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if bin_override == "MOCK":
        env["AGENT_HANDBRAKE_BIN"] = make_mock()
    elif bin_override is not None:
        env["AGENT_HANDBRAKE_BIN"] = bin_override
    else:
        env.pop("AGENT_HANDBRAKE_BIN", None)
    env.pop("MOCK_HB_FAIL", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(TOOL), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
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
        require("media provider: handbrake" in r.stdout, "help should name the provider")
        require("convert <input>" in r.stdout, "help should document convert")

    check("--help lists commands", test_help)

    def test_unknown_command():
        r = run_tool("bogus", bin_override=None)
        require(r.returncode == 2, f"unknown command should exit 2, got {r.returncode}")

    check("unknown command exits 2", test_unknown_command)

    def test_presets_json():
        r = run_tool("presets", "--json")
        require(r.returncode == 0, f"presets should succeed: {r.stderr}")
        cats = json.loads(r.stdout)["result"]["categories"]
        by_name = {c["category"]: c["presets"] for c in cats}
        require("General" in by_name, f"General category parsed: {by_name}")
        require("Fast 1080p30" in by_name["General"], f"preset names parsed: {by_name}")
        require(len(by_name["General"]) == 3, f"descriptions must not parse as presets: {by_name}")

    check("presets parses categories without descriptions", test_presets_json)

    def test_scan_json():
        with tempfile.NamedTemporaryFile(suffix=".mkv") as f:
            r = run_tool("scan", f.name, "--json")
            require(r.returncode == 0, f"scan should succeed: {r.stderr}")
            result = json.loads(r.stdout)["result"]
            require(len(result["titles"]) == 1, f"one title expected: {result}")
            t = result["titles"][0]
            require(t["duration"] == "1:52:30", f"duration parsed: {t}")
            require(t["resolution"] == "1920x1080", f"geometry parsed: {t}")
            require(t["audio_tracks"][0]["language"] == "English", f"audio parsed: {t}")
            require(t["subtitle_count"] == 2, f"subtitles counted: {t}")

    check("scan parses JSON Title Set", test_scan_json)

    def test_scan_missing_input():
        r = run_tool("scan", "/nonexistent/file.mkv", "--json")
        require(r.returncode != 0, "scan of a missing file should fail")
        data = json.loads(r.stdout)
        require(data["success"] is False, f"should report failure: {data}")

    check("scan of missing input fails cleanly", test_scan_missing_input)

    def test_convert_default_output():
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "title_t00.mkv"
            src.write_bytes(b"x" * 1024)
            r = run_tool("convert", str(src))
            require(r.returncode == 0, f"convert should succeed: {r.stderr}")
            out = Path(d) / "title_t00.mp4"
            require(out.exists() and out.stat().st_size > 0, "mp4 lands next to input")
            # convert auto-verifies; output should mention the file.
            require("title_t00.mp4" in r.stdout, f"convert should verify output: {r.stdout!r}")

    check("convert writes sibling mp4 and auto-verifies", test_convert_default_output)

    def test_convert_into_directory():
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "movie.mkv"
            src.write_bytes(b"x")
            dest = Path(d) / "plex"
            dest.mkdir()
            r = run_tool("convert", str(src), str(dest), "--json")
            require(r.returncode == 0, f"convert should succeed: {r.stderr}")
            require((dest / "movie.mp4").exists(), "mp4 lands inside the directory")
            data = json.loads(r.stdout)
            require(data["result"]["count"] == 1, f"verify payload expected: {data}")

    check("convert with directory output nests the mp4", test_convert_into_directory)

    def test_batch_and_skip():
        with tempfile.TemporaryDirectory() as d:
            indir, outdir = Path(d) / "rips", Path(d) / "plex"
            indir.mkdir()
            (indir / "a.mkv").write_bytes(b"x")
            (indir / "b.mkv").write_bytes(b"x")
            (indir / "notes.txt").write_bytes(b"x")
            r = run_tool("batch", str(indir), str(outdir), "--json")
            require(r.returncode == 0, f"batch should succeed: {r.stderr}")
            data = json.loads(r.stdout)["result"]
            require(data["converted"] == 2, f"both mkvs converted: {data}")
            require(data["count"] == 2, f"non-mkv files ignored: {data}")
            # Second run skips everything already converted.
            r2 = run_tool("batch", str(indir), str(outdir), "--json")
            data2 = json.loads(r2.stdout)["result"]
            require(data2["skipped"] == 2 and data2["converted"] == 0,
                    f"existing outputs should be skipped: {data2}")
            # --overwrite re-encodes.
            r3 = run_tool("batch", str(indir), str(outdir), "--overwrite", "--json")
            data3 = json.loads(r3.stdout)["result"]
            require(data3["converted"] == 2, f"--overwrite should re-encode: {data3}")

    check("batch converts, skips existing, honors --overwrite", test_batch_and_skip)

    def test_failed_encode_leaves_no_partial():
        with tempfile.TemporaryDirectory() as d:
            indir, outdir = Path(d) / "rips", Path(d) / "plex"
            indir.mkdir()
            (indir / "a.mkv").write_bytes(b"x")
            r = run_tool("batch", str(indir), str(outdir), "--json",
                         extra_env={"MOCK_HB_FAIL": "1"})
            require(r.returncode != 0, "batch with a failed encode should exit non-zero")
            data = json.loads(r.stdout)["result"]
            require(data["failed"] == 1, f"failure tallied: {data}")
            leftovers = list(outdir.iterdir()) if outdir.exists() else []
            require(not leftovers, f"failed encode must leave nothing behind: {leftovers}")
            # A later run must re-attempt (not skip) the failed file.
            r2 = run_tool("batch", str(indir), str(outdir), "--json")
            data2 = json.loads(r2.stdout)["result"]
            require(data2["converted"] == 1 and data2["skipped"] == 0,
                    f"retry should convert, not skip: {data2}")

    check("failed encode leaves no partial mp4 and is retried", test_failed_encode_leaves_no_partial)

    def test_missing_operands_exit_2():
        for args in (["scan"], ["convert"], ["batch"], ["batch", "/tmp"], ["verify"]):
            r = run_tool(*args, "--json")
            require(r.returncode == 2, f"{args} should exit 2, got {r.returncode}")
            data = json.loads(r.stdout)
            require(data["success"] is False and "required" in data["error"],
                    f"{args} should explain the missing operand: {data}")
        r = run_tool("convert", "in.mkv", "--preset")
        require(r.returncode == 2, f"--preset with no value should exit 2, got {r.returncode}")

    check("missing operands return structured exit-2 errors", test_missing_operands_exit_2)

    def test_snapshot_dry_run():
        r = run_tool("snapshot", "--dry-run")
        require(r.returncode == 0, f"snapshot --dry-run should exit 0: {r.stderr}")
        require("--version" in r.stdout and "--preset-list" in r.stdout,
                f"dry-run should print both commands: {r.stdout!r}")

    check("snapshot honors --dry-run", test_snapshot_dry_run)

    def test_dry_run():
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.mkv"
            src.write_bytes(b"x")
            r = run_tool("convert", str(src), "--dry-run", "--preset", "HQ 1080p30 Surround")
            require(r.returncode == 0, "dry-run should exit 0")
            require("--preset HQ\\ 1080p30\\ Surround" in r.stdout,
                    f"dry-run should print the command with the preset: {r.stdout!r}")
            require(not (Path(d) / "in.mp4").exists(), "dry-run must not write output")

    check("--dry-run prints command without encoding", test_dry_run)

    def test_missing_binary():
        r = run_tool("presets", "--json", bin_override="/nonexistent/HandBrakeCLI")
        require(r.returncode == 127, f"missing binary should exit 127, got {r.returncode}")
        data = json.loads(r.stdout)
        require(data["success"] is False, f"should report failure: {data}")
        require("not found" in data["error"], f"error should explain: {data}")

    check("missing binary errors with exit 127", test_missing_binary)

    def test_verify_no_binary_needed():
        with tempfile.TemporaryDirectory() as outdir:
            r = run_tool("verify", outdir, bin_override="/nonexistent")
            require(r.returncode == 0, "verify needs no binary")
            require("No .mp4" in r.stdout, f"empty verify message: {r.stdout!r}")

    check("verify works without HandBrakeCLI", test_verify_no_binary_needed)

    def test_version():
        r = run_tool("version")
        require(r.returncode == 0, f"version should succeed: {r.stderr}")
        require("HandBrake 1.7.3" in r.stdout, f"clean version expected: {r.stdout!r}")

    check("version reports clean banner", test_version)

    def test_snapshot():
        r = run_tool("snapshot", "--json")
        require(r.returncode == 0, f"snapshot should succeed: {r.stderr}")
        snap = json.loads(r.stdout)["result"]
        require(snap["version"] == "HandBrake 1.7.3", f"version in snapshot: {snap}")
        require(snap["preset_count"] == 4, f"preset count in snapshot: {snap}")
        require(snap["default_preset"] == "Fast 1080p30", f"default preset: {snap}")

    check("snapshot reports version and preset count", test_snapshot)

    print(f"\nhandbrake tests: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
