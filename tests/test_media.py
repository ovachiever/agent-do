#!/usr/bin/env python3
"""Focused coverage for the media family tool.

The family owns neutral verbs (drives/scan/rip/convert/batch/presets/verify)
and routes each to a provider under tools/agent-media/providers/. These tests
point AGENT_DO_MEDIA_PROVIDER_DIR at stub providers so no disc drive or
HandBrakeCLI is needed, and cover: help, provider readiness, polymorphic scan
routing, delegation payloads, passthrough, family-owned verify, the degraded
snapshot when a provider is missing, and the unknown-command path.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# A stub provider that echoes what it was asked to do. `version --dry-run`
# exits 0 unless STUB_ENGINE_MISSING is set, mirroring the real providers'
# readiness contract (127 when the engine binary cannot be resolved).
STUB = """\
#!/usr/bin/env bash
name="{name}"
if [[ "${{1:-}}" == "version" && "${{2:-}}" == "--dry-run" ]]; then
  [[ -n "${{STUB_ENGINE_MISSING:-}}" ]] && exit 127
  exit 0
fi
json=false
args=()
for a in "$@"; do
  [[ "$a" == "--json" ]] && json=true || args+=("$a")
done
case "${{args[0]:-}}" in
  snapshot)
    if $json; then
      if [[ "$name" == "makemkv" ]]; then
        echo '{{"success":true,"result":{{"version":"1.17.7","drives":[{{"drive_name":"BD-RE PIONEER","disc_name":"MY_MOVIE"}}]}}}}'
      else
        echo '{{"success":true,"result":{{"version":"1.7.3","preset_count":3,"default_preset":"Fast 1080p30"}}}}'
      fi
    else
      echo "$name snapshot"
    fi
    ;;
  version)
    if $json; then echo '{{"success":true,"result":{{"version":"9.9.9"}}}}'; else echo "$name 9.9.9"; fi
    ;;
  *)
    if $json; then
      printf '{{"success":true,"provider":"%s","args":[' "$name"
      first=true
      for a in "${{args[@]}}"; do
        $first || printf ','
        printf '"%s"' "$a"
        first=false
      done
      printf ']}}\\n'
    else
      echo "$name:${{args[*]}}"
    fi
    ;;
esac
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, env=env, timeout=60)


def main() -> int:
    help_result = run(["./agent-do", "media", "--help"])
    require(help_result.returncode == 0, f"media help failed: {help_result.stderr}")
    require("Unified media ripping and conversion" in help_result.stdout, f"unexpected media help: {help_result.stdout}")
    for verb in ("drives", "scan", "rip", "convert", "batch", "presets", "verify", "makemkv", "handbrake"):
        require(f"\n  {verb}" in help_result.stdout, f"help missing verb {verb}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        providers = tmp / "providers"
        providers.mkdir()
        write_stub(providers / "makemkv", STUB.format(name="makemkv"))
        write_stub(providers / "handbrake", STUB.format(name="handbrake"))

        env = os.environ.copy()
        env["AGENT_DO_MEDIA_PROVIDER_DIR"] = str(providers)
        env.pop("STUB_ENGINE_MISSING", None)

        # providers: both ready
        r = run(["./agent-do", "media", "providers", "--json"], env=env)
        require(r.returncode == 0, f"providers failed: {r.stderr}")
        listed = {p["name"]: p for p in json.loads(r.stdout)["providers"]}
        require(set(listed) == {"makemkv", "handbrake"}, f"unexpected providers: {listed}")
        require(all(p["ready"] and p["available"] for p in listed.values()), f"providers should be ready: {listed}")
        require(listed["makemkv"]["role"] == "disc" and listed["handbrake"]["role"] == "transcode", f"roles: {listed}")

        r = run(["./agent-do", "media", "providers"], env=env)
        require("makemkv    ready" in r.stdout and "handbrake  ready" in r.stdout, f"text providers: {r.stdout}")

        # engine missing -> ready false, available true
        missing_env = dict(env, STUB_ENGINE_MISSING="1")
        r = run(["./agent-do", "media", "providers", "--json"], env=missing_env)
        listed = {p["name"]: p for p in json.loads(r.stdout)["providers"]}
        require(all(p["available"] and not p["ready"] for p in listed.values()), f"engine-missing readiness: {listed}")

        # scan routes by operand
        def scan(target: str, *extra: str) -> dict:
            res = run(["./agent-do", "media", "scan", target, *extra, "--json"], env=env)
            require(res.returncode == 0, f"scan {target} failed: {res.stderr} {res.stdout}")
            return json.loads(res.stdout)

        for disc in ("disc:0", "0", "dev:/dev/rdisk2", "iso:/x.iso", "file:/x.iso"):
            payload = scan(disc)
            require(payload["provider"] == "makemkv", f"{disc} should route to makemkv: {payload}")
            require(payload["command"][:2] == ["info", disc], f"{disc} command: {payload}")
        payload = scan("/tmp/movie.ISO")
        require(payload["provider"] == "makemkv" and payload["command"] == ["info", "iso:/tmp/movie.ISO"],
                f"bare .iso should become iso: for makemkv: {payload}")
        payload = scan("/tmp/movie.mkv")
        require(payload["provider"] == "handbrake" and payload["command"] == ["scan", "/tmp/movie.mkv"],
                f"file should route to handbrake: {payload}")
        payload = scan("/tmp/movie.mkv", "--provider", "makemkv")
        require(payload["provider"] == "makemkv", f"--provider must override routing: {payload}")
        require(payload["result"]["args"] == ["info", "/tmp/movie.mkv"], f"--provider must be stripped: {payload}")

        # family verbs delegate 1:1 with flags passed through; --json reaches the provider
        r = run(["./agent-do", "media", "rip", "disc:0", "all", "/tmp/out", "--minlength", "300", "--json"], env=env)
        payload = json.loads(r.stdout)
        require(payload["success"] is True and payload["tool"] == "media", f"rip payload: {payload}")
        require(payload["provider"] == "makemkv", f"rip provider: {payload}")
        require(payload["command"] == ["rip", "disc:0", "all", "/tmp/out", "--minlength", "300"], f"rip command: {payload}")
        require(payload["result"]["args"] == ["rip", "disc:0", "all", "/tmp/out", "--minlength", "300"],
                f"provider must receive the flags: {payload}")

        r = run(["./agent-do", "media", "convert", "/tmp/a.mkv", "/tmp/a.mp4", "--preset", "HQ 1080p30 Surround", "--json"], env=env)
        payload = json.loads(r.stdout)
        require(payload["provider"] == "handbrake" and payload["command"][0] == "convert", f"convert payload: {payload}")
        require("HQ 1080p30 Surround" in payload["result"]["args"], f"preset must pass through intact: {payload}")

        r = run(["./agent-do", "media", "batch", "/tmp/in", "/tmp/out", "--overwrite", "--json"], env=env)
        payload = json.loads(r.stdout)
        require(payload["provider"] == "handbrake" and payload["command"] == ["batch", "/tmp/in", "/tmp/out", "--overwrite"],
                f"batch payload: {payload}")

        r = run(["./agent-do", "media", "drives", "--json"], env=env)
        require(json.loads(r.stdout)["command"] == ["drives"], f"drives payload: {r.stdout}")
        r = run(["./agent-do", "media", "presets", "--json"], env=env)
        require(json.loads(r.stdout)["provider"] == "handbrake", f"presets payload: {r.stdout}")

        # text mode execs the provider directly: output passes through verbatim
        r = run(["./agent-do", "media", "rip", "disc:0", "all", "/tmp/out"], env=env)
        require(r.returncode == 0 and r.stdout.strip() == "makemkv:rip disc:0 all /tmp/out", f"text rip: {r.stdout!r} {r.stderr}")

        # passthrough reaches provider-only verbs
        r = run(["./agent-do", "media", "makemkv", "backup", "disc:0", "/tmp/bk", "--json"], env=env)
        payload = json.loads(r.stdout)
        require(payload["provider"] == "makemkv" and payload["command"] == ["backup", "disc:0", "/tmp/bk"], f"passthrough: {payload}")
        r = run(["./agent-do", "media", "handbrake"], env=env)
        require(r.returncode == 1 and "Subcommand required" in r.stderr, f"bare passthrough must ask for a subcommand: {r.stderr}")

        # snapshot: composite, per-provider
        r = run(["./agent-do", "media", "snapshot", "--json"], env=env)
        require(r.returncode == 0, f"snapshot failed: {r.stderr}")
        snap = json.loads(r.stdout)
        require(snap["tool"] == "media" and snap["ready_count"] == 2 and snap["provider_count"] == 2, f"snapshot counts: {snap}")
        require(snap["providers"]["makemkv"]["snapshot"]["drives"][0]["disc_name"] == "MY_MOVIE", f"makemkv snapshot: {snap}")
        require(snap["providers"]["handbrake"]["snapshot"]["preset_count"] == 3, f"handbrake snapshot: {snap}")
        require(snap["providers"]["makemkv"]["version"] == "1.17.7", f"version lifted: {snap}")

        r = run(["./agent-do", "media", "snapshot"], env=env)
        require("2 of 2 ready" in r.stdout and "drives: 1" in r.stdout and "presets: 3" in r.stdout, f"text snapshot: {r.stdout}")

        r = run(["./agent-do", "media", "version", "--json"], env=env)
        ver = json.loads(r.stdout)
        require(ver["providers"]["handbrake"]["version"] == "9.9.9", f"version: {ver}")

        # degraded: handbrake provider script removed, makemkv engine missing
        (providers / "handbrake").unlink()
        r = run(["./agent-do", "media", "snapshot", "--json"], env=missing_env)
        require(r.returncode == 0, f"degraded snapshot must still succeed: {r.stderr}")
        snap = json.loads(r.stdout)
        require(snap["ready_count"] == 0, f"degraded ready_count: {snap}")
        hb = snap["providers"]["handbrake"]
        require(hb["available"] is False and hb["ready"] is False and "missing" in hb["error"], f"degraded handbrake: {hb}")
        mk = snap["providers"]["makemkv"]
        require(mk["available"] is True and mk["ready"] is False and "error" in mk, f"degraded makemkv: {mk}")

        r = run(["./agent-do", "media", "convert", "/tmp/a.mkv", "--json"], env=env)
        require(r.returncode == 1, "convert without the handbrake provider must fail")
        require(json.loads(r.stdout)["success"] is False, f"missing provider must be a structured error: {r.stdout}")

        # family-owned verify covers both pipeline stages and needs no engine
        outdir = tmp / "out"
        outdir.mkdir()
        (outdir / "title_t00.mkv").write_bytes(b"x" * 2048)
        (outdir / "movie.mp4").write_bytes(b"y" * 1024)
        (outdir / "partial.mkv").write_bytes(b"")
        (outdir / "notes.txt").write_text("ignored")
        r = run(["./agent-do", "media", "verify", str(outdir), "--json"], env=env)
        require(r.returncode == 0, f"verify failed: {r.stderr}")
        result = json.loads(r.stdout)["result"]
        require(result["count"] == 3 and result["by_kind"] == {"mkv": 2, "mp4": 1}, f"verify counts: {result}")
        incomplete = [f["file"] for f in result["files"] if not f["complete"]]
        require(incomplete == ["partial.mkv"], f"verify completeness: {result}")
        r = run(["./agent-do", "media", "verify", str(outdir)], env=env)
        require("3 file(s) (2 mkv, 1 mp4)" in r.stdout and "(empty)" in r.stdout, f"verify text: {r.stdout}")
        r = run(["./agent-do", "media", "verify"], env=env)
        require(r.returncode == 2, f"verify without a path must exit 2: {r.returncode} {r.stderr}")
        r = run(["./agent-do", "media", "verify", str(tmp / "nope")], env=env)
        require(r.returncode == 1 and "Not found" in r.stderr, f"verify missing path: {r.stderr}")

        # unknown command
        r = run(["./agent-do", "media", "frobnicate"], env=env)
        require(r.returncode == 1 and "Unknown command" in r.stderr, f"unknown command: {r.stderr}")

    # the providers are engines, not top-level tools
    listing = run(["./agent-do", "--list"])
    require(listing.returncode == 0, f"--list failed: {listing.stderr}")
    tools = {line.split()[0] for line in listing.stdout.splitlines() if line.startswith("  ") and len(line.split()) > 1}
    require("media" in tools, f"media must be a listed tool: {sorted(tools)[:5]}...")
    require(not tools & {"makemkv", "handbrake"}, f"providers must not surface as top-level tools: {sorted(tools & {'makemkv', 'handbrake'})}")

    print("media tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
