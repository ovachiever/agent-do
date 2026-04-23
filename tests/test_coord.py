#!/usr/bin/env python3
"""Focused coverage for the coord state-and-interrupt broker."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def iso_ago(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        subprocess.run(["git", "init", "-q"], cwd=project, check=True)

        env_base = dict(os.environ)
        env_base["AGENT_DO_HOME"] = str(fake_home)

        env_a = dict(env_base)
        env_a["CODEX_THREAD_ID"] = "alpha-123"

        env_b = dict(env_base)
        env_b["CODEX_THREAD_ID"] = "beta-456"

        help_result = run([str(AGENT_DO), "coord", "--help"], cwd=project, env=env_a)
        require(help_result.returncode == 0, f"coord help failed: {help_result.stderr}")
        require("state and interrupt broker" in help_result.stdout.lower(), f"unexpected help: {help_result.stdout}")

        whoami = run([str(AGENT_DO), "coord", "whoami", "--json"], cwd=project, env=env_a)
        require(whoami.returncode == 0, f"coord whoami failed: {whoami.stderr}")
        whoami_payload = json.loads(whoami.stdout)
        require(whoami_payload["agent_id"] == "codex-alpha123", f"unexpected whoami payload: {whoami_payload}")
        require(whoami_payload["status"] == "active", f"unexpected whoami payload: {whoami_payload}")
        require(whoami_payload["active_window_seconds"] == 900, f"unexpected active window: {whoami_payload}")

        alias_a = run([str(AGENT_DO), "coord", "alias", "reviewer", "--json"], cwd=project, env=env_a)
        require(alias_a.returncode == 0, f"coord alias reviewer failed: {alias_a.stderr}")
        alias_b = run([str(AGENT_DO), "coord", "alias", "infra", "--json"], cwd=project, env=env_b)
        require(alias_b.returncode == 0, f"coord alias infra failed: {alias_b.stderr}")

        touch_a = run([str(AGENT_DO), "coord", "touch", "--json"], cwd=project, env=env_a)
        require(touch_a.returncode == 0, f"coord touch a failed: {touch_a.stderr}")
        touch_b = run([str(AGENT_DO), "coord", "touch", "--json"], cwd=project, env=env_b)
        require(touch_b.returncode == 0, f"coord touch b failed: {touch_b.stderr}")
        touch_b_payload = json.loads(touch_b.stdout)
        require(len(touch_b_payload["active_peers"]) == 1, f"expected one active peer: {touch_b_payload}")

        aliases = run([str(AGENT_DO), "coord", "aliases", "--json"], cwd=project, env=env_a)
        require(aliases.returncode == 0, f"coord aliases failed: {aliases.stderr}")
        alias_names = sorted(item["alias"] for item in json.loads(aliases.stdout)["aliases"])
        require(alias_names == ["infra", "reviewer"], f"unexpected aliases payload: {aliases.stdout}")

        focus_a = run(
            [
                str(AGENT_DO),
                "coord",
                "focus",
                "set",
                "private Render networking",
                "--path",
                "recognition-oracle/render.yaml",
                "--path",
                "dm-ck/render.yaml",
                "--json",
            ],
            cwd=project,
            env=env_a,
        )
        require(focus_a.returncode == 0, f"coord focus set failed: {focus_a.stderr}")

        claim_a = run(
            [
                str(AGENT_DO),
                "coord",
                "claim",
                "recognition-oracle/render.yaml",
                "--reason",
                "private Render blueprint wiring",
                "--strength",
                "strong",
                "--json",
            ],
            cwd=project,
            env=env_a,
        )
        require(claim_a.returncode == 0, f"coord claim failed: {claim_a.stderr}")
        claim_payload = json.loads(claim_a.stdout)
        require(claim_payload["claim"]["strength"] == "strong", f"unexpected claim payload: {claim_payload}")

        need_b = run(
            [
                str(AGENT_DO),
                "coord",
                "need",
                "add",
                "dm-sdk@1.2.2",
                "--why",
                "switch off tarball dependency",
                "--json",
            ],
            cwd=project,
            env=env_b,
        )
        require(need_b.returncode == 0, f"coord need add failed: {need_b.stderr}")

        interrupts_b_before = run([str(AGENT_DO), "coord", "interrupts", "--json"], cwd=project, env=env_b)
        require(interrupts_b_before.returncode == 0, f"coord interrupts before failed: {interrupts_b_before.stderr}")
        interrupts_before_payload = json.loads(interrupts_b_before.stdout)
        require(interrupts_before_payload["counts"]["dependency"] == 0, f"unexpected interrupts before publish: {interrupts_before_payload}")

        publish_a = run(
            [
                str(AGENT_DO),
                "coord",
                "publish",
                "add",
                "dm-sdk@1.2.2",
                "--status",
                "ready",
                "--summary",
                "private package published",
                "--ref",
                "commit:abc123",
                "--json",
            ],
            cwd=project,
            env=env_a,
        )
        require(publish_a.returncode == 0, f"coord publish failed: {publish_a.stderr}")

        interrupts_b_after = run([str(AGENT_DO), "coord", "interrupts", "--json", "--mark-seen"], cwd=project, env=env_b)
        require(interrupts_b_after.returncode == 0, f"coord interrupts after failed: {interrupts_b_after.stderr}")
        after_payload = json.loads(interrupts_b_after.stdout)
        dependency_interrupts = [item for item in after_payload["interrupts"] if item["kind"] == "dependency"]
        require(len(dependency_interrupts) == 1, f"expected dependency interrupt: {after_payload}")
        require(dependency_interrupts[0]["keys"] == ["dm-sdk@1.2.2"], f"unexpected dependency interrupt: {dependency_interrupts}")
        require(dependency_interrupts[0]["new"] is True, f"expected new dependency interrupt: {dependency_interrupts}")

        focus_b = run(
            [
                str(AGENT_DO),
                "coord",
                "focus",
                "set",
                "render blueprint review",
                "--path",
                "recognition-oracle/render.yaml",
                "--json",
            ],
            cwd=project,
            env=env_b,
        )
        require(focus_b.returncode == 0, f"coord focus b failed: {focus_b.stderr}")

        interrupts_b_overlap = run([str(AGENT_DO), "coord", "interrupts", "--json"], cwd=project, env=env_b)
        require(interrupts_b_overlap.returncode == 0, f"coord interrupts overlap failed: {interrupts_b_overlap.stderr}")
        overlap_payload = json.loads(interrupts_b_overlap.stdout)
        contentions = [item for item in overlap_payload["interrupts"] if item["kind"] == "contention"]
        require(len(contentions) == 1, f"expected one contention interrupt: {overlap_payload}")
        require("recognition-oracle/render.yaml" in contentions[0]["paths"], f"unexpected contention payload: {contentions}")

        _ = run([str(AGENT_DO), "coord", "interrupts", "--json", "--mark-seen"], cwd=project, env=env_b)

        release_a = run(
            [str(AGENT_DO), "coord", "release", "recognition-oracle/render.yaml", "--json"],
            cwd=project,
            env=env_a,
        )
        require(release_a.returncode == 0, f"coord release failed: {release_a.stderr}")
        clear_focus_a = run([str(AGENT_DO), "coord", "focus", "clear", "--json"], cwd=project, env=env_a)
        require(clear_focus_a.returncode == 0, f"coord focus clear failed: {clear_focus_a.stderr}")

        interrupts_b_novelty = run([str(AGENT_DO), "coord", "interrupts", "--json"], cwd=project, env=env_b)
        require(interrupts_b_novelty.returncode == 0, f"coord interrupts novelty failed: {interrupts_b_novelty.stderr}")
        novelty_payload = json.loads(interrupts_b_novelty.stdout)
        novelty = [item for item in novelty_payload["interrupts"] if item["kind"] == "novelty"]
        require(novelty, f"expected novelty interrupt after release/clear: {novelty_payload}")

        status_b = run([str(AGENT_DO), "coord", "status", "--json"], cwd=project, env=env_b)
        require(status_b.returncode == 0, f"coord status failed: {status_b.stderr}")
        status_payload = json.loads(status_b.stdout)
        require(status_payload["focus"]["goal"] == "render blueprint review", f"unexpected status payload: {status_payload}")
        require(len(status_payload["needs"]) == 1, f"unexpected status needs: {status_payload}")

        claims = run([str(AGENT_DO), "coord", "claims", "--json"], cwd=project, env=env_b)
        require(claims.returncode == 0, f"coord claims failed: {claims.stderr}")
        claims_payload = json.loads(claims.stdout)
        require(claims_payload["claims"] == [], f"expected claims to be empty after release: {claims_payload}")

        agents_path = project / ".git" / "agent-do" / "coord" / "agents.json"
        agents_payload = json.loads(agents_path.read_text())
        agents_payload["agents"]["codex-alpha123"]["lease_expires_at"] = iso_ago(3600)
        agents_payload["agents"]["codex-alpha123"]["last_seen"] = iso_ago(3600)
        agents_path.write_text(json.dumps(agents_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        peers_idle = run([str(AGENT_DO), "coord", "peers", "--json", "--all"], cwd=project, env=env_b)
        require(peers_idle.returncode == 0, f"coord peers idle failed: {peers_idle.stderr}")
        peers_idle_payload = json.loads(peers_idle.stdout)
        alpha_peer = next(item for item in peers_idle_payload["peers"] if item["agent_id"] == "codex-alpha123")
        require(alpha_peer["status"] == "idle", f"expected idle peer: {peers_idle_payload}")

        agents_payload = json.loads(agents_path.read_text())
        agents_payload["agents"]["codex-alpha123"]["lease_expires_at"] = iso_ago(30 * 24 * 3600)
        agents_payload["agents"]["codex-alpha123"]["last_seen"] = iso_ago(30 * 24 * 3600)
        agents_path.write_text(json.dumps(agents_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        peers_default = run([str(AGENT_DO), "coord", "peers", "--json"], cwd=project, env=env_b)
        require(peers_default.returncode == 0, f"coord peers default failed: {peers_default.stderr}")
        peers_default_payload = json.loads(peers_default.stdout)
        require(
            all(item["agent_id"] != "codex-alpha123" for item in peers_default_payload["peers"]),
            f"expected stale peer to be hidden by default: {peers_default_payload}",
        )

    print("coord tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
