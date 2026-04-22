#!/usr/bin/env python3
"""Focused coverage for the coord mailbox tool."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
        require("Project-local agent coordination mailbox" in help_result.stdout, f"unexpected help: {help_result.stdout}")

        whoami = run([str(AGENT_DO), "coord", "whoami", "--json"], cwd=project, env=env_a)
        require(whoami.returncode == 0, f"coord whoami failed: {whoami.stderr}")
        whoami_payload = json.loads(whoami.stdout)
        require(whoami_payload["agent_id"] == "codex-alpha123", f"unexpected whoami payload: {whoami_payload}")
        require(whoami_payload["storage"] == "git-local", f"unexpected storage payload: {whoami_payload}")

        alias_a = run([str(AGENT_DO), "coord", "alias", "reviewer", "--json"], cwd=project, env=env_a)
        require(alias_a.returncode == 0, f"coord alias reviewer failed: {alias_a.stderr}")
        alias_b = run([str(AGENT_DO), "coord", "alias", "infra", "--json"], cwd=project, env=env_b)
        require(alias_b.returncode == 0, f"coord alias infra failed: {alias_b.stderr}")

        aliases = run([str(AGENT_DO), "coord", "aliases", "--json"], cwd=project, env=env_a)
        require(aliases.returncode == 0, f"coord aliases failed: {aliases.stderr}")
        aliases_payload = json.loads(aliases.stdout)
        alias_names = [item["alias"] for item in aliases_payload["aliases"]]
        require(alias_names == ["reviewer", "infra"] or alias_names == ["infra", "reviewer"], f"unexpected aliases payload: {aliases_payload}")

        peers = run([str(AGENT_DO), "coord", "peers", "--json"], cwd=project, env=env_a)
        require(peers.returncode == 0, f"coord peers failed: {peers.stderr}")
        peers_payload = json.loads(peers.stdout)
        peer_ids = [item["agent_id"] for item in peers_payload["peers"]]
        require(peer_ids == ["codex-alpha123", "codex-beta456"], f"unexpected peers payload: {peers_payload}")

        handoff = run(
            [
                str(AGENT_DO),
                "coord",
                "handoff",
                "infra",
                "--summary",
                "Local verification is done.",
                "--ref",
                "recognition-oracle/app/api/generate/route.ts",
                "--check",
                "cd recognition-oracle && RESEND_API_KEY=re_dummy npm run build",
                "--next",
                "publish dm-sdk 1.2.2",
                "--json",
            ],
            cwd=project,
            env=env_a,
        )
        require(handoff.returncode == 0, f"coord handoff failed: {handoff.stderr}")
        handoff_payload = json.loads(handoff.stdout)
        message = handoff_payload["message"]
        message_id = message["id"]
        thread_id = message["thread_id"]
        require(message["kind"] == "handoff", f"unexpected handoff payload: {handoff_payload}")
        require(message["to"] == ["codex-beta456"], f"unexpected handoff recipients: {handoff_payload}")

        inbox_b = run([str(AGENT_DO), "coord", "inbox", "--json"], cwd=project, env=env_b)
        require(inbox_b.returncode == 0, f"coord inbox failed: {inbox_b.stderr}")
        inbox_b_payload = json.loads(inbox_b.stdout)
        require(len(inbox_b_payload["messages"]) == 1, f"unexpected inbox payload: {inbox_b_payload}")
        require(inbox_b_payload["messages"][0]["id"] == message_id, f"unexpected inbox message: {inbox_b_payload}")

        ack = run([str(AGENT_DO), "coord", "ack", message_id, "--json"], cwd=project, env=env_b)
        require(ack.returncode == 0, f"coord ack failed: {ack.stderr}")
        ack_payload = json.loads(ack.stdout)
        require(ack_payload["message"]["acks"][0]["agent_id"] == "codex-beta456", f"unexpected ack payload: {ack_payload}")

        read = run([str(AGENT_DO), "coord", "read", message_id, "--json"], cwd=project, env=env_b)
        require(read.returncode == 0, f"coord read failed: {read.stderr}")
        read_payload = json.loads(read.stdout)
        require(read_payload["message"]["refs"] == ["recognition-oracle/app/api/generate/route.ts"], f"unexpected refs: {read_payload}")
        require(read_payload["message"]["checks"] == ["cd recognition-oracle && RESEND_API_KEY=re_dummy npm run build"], f"unexpected checks: {read_payload}")
        require(read_payload["message"]["next"] == ["publish dm-sdk 1.2.2"], f"unexpected next steps: {read_payload}")

        reply = run(
            [
                str(AGENT_DO),
                "coord",
                "reply",
                message_id,
                "--body",
                "No direct conflict, but two rollout gotchas.",
                "--json",
            ],
            cwd=project,
            env=env_b,
        )
        require(reply.returncode == 0, f"coord reply failed: {reply.stderr}")
        reply_payload = json.loads(reply.stdout)
        require(reply_payload["message"]["thread_id"] == thread_id, f"unexpected reply thread: {reply_payload}")
        require(reply_payload["message"]["to"] == ["codex-alpha123"], f"unexpected reply recipients: {reply_payload}")

        inbox_a = run([str(AGENT_DO), "coord", "inbox", "--json"], cwd=project, env=env_a)
        require(inbox_a.returncode == 0, f"coord inbox a failed: {inbox_a.stderr}")
        inbox_a_payload = json.loads(inbox_a.stdout)
        reply_messages = [item for item in inbox_a_payload["messages"] if item["kind"] == "reply"]
        require(len(reply_messages) == 1, f"unexpected inbox a payload: {inbox_a_payload}")
        require(reply_messages[0]["thread_id"] == thread_id, f"unexpected reply thread payload: {reply_messages}")

        thread = run([str(AGENT_DO), "coord", "thread", thread_id, "--json"], cwd=project, env=env_a)
        require(thread.returncode == 0, f"coord thread failed: {thread.stderr}")
        thread_payload = json.loads(thread.stdout)
        require(len(thread_payload["messages"]) == 2, f"unexpected thread payload: {thread_payload}")

        claim = run(
            [
                str(AGENT_DO),
                "coord",
                "claim",
                "recognition-oracle/render.yaml",
                "--reason",
                "private Render blueprint wiring",
                "--json",
            ],
            cwd=project,
            env=env_a,
        )
        require(claim.returncode == 0, f"coord claim failed: {claim.stderr}")
        claim_payload = json.loads(claim.stdout)
        require(claim_payload["claim"]["owner"] == "codex-alpha123", f"unexpected claim payload: {claim_payload}")

        claims = run([str(AGENT_DO), "coord", "claims", "--json"], cwd=project, env=env_b)
        require(claims.returncode == 0, f"coord claims failed: {claims.stderr}")
        claims_payload = json.loads(claims.stdout)
        require(claims_payload["claims"][0]["owner_alias"] == "reviewer", f"unexpected claims payload: {claims_payload}")

        conflict_claim = run(
            [
                str(AGENT_DO),
                "coord",
                "claim",
                "recognition-oracle/render.yaml",
                "--reason",
                "conflicting work",
                "--json",
            ],
            cwd=project,
            env=env_b,
        )
        require(conflict_claim.returncode != 0, "expected conflicting claim to fail")
        conflict_payload = json.loads(conflict_claim.stdout)
        require("already claimed" in conflict_payload["error"], f"unexpected conflict payload: {conflict_payload}")

        release = run([str(AGENT_DO), "coord", "release", "recognition-oracle/render.yaml", "--json"], cwd=project, env=env_a)
        require(release.returncode == 0, f"coord release failed: {release.stderr}")

        claim_b = run(
            [
                str(AGENT_DO),
                "coord",
                "claim",
                "recognition-oracle/render.yaml",
                "--reason",
                "infra follow-up",
                "--json",
            ],
            cwd=project,
            env=env_b,
        )
        require(claim_b.returncode == 0, f"coord claim b failed: {claim_b.stderr}")

    print("coord tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
