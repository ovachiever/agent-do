#!/usr/bin/env python3
"""psql describe works for a table outside the public schema.

D69 (2026-10-01): `describe watcher.digest_runs` answered "not found or
query failed" for a table that exists. Cause: index sizes were read with
pg_relation_size(quote_ident(indexname)) — an unqualified name, resolved via
search_path, so any non-public index raised "relation … does not exist" and
the whole describe failed. This test runs a throwaway PostgreSQL cluster
(initdb on a temp dir, 127.0.0.1, random port) and skips when no server
binaries are installed.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find_pg_bin() -> Path | None:
    initdb = shutil.which("initdb")
    if initdb:
        return Path(initdb).parent
    for version in ("18", "17", "16", "15", "14"):
        candidate = Path(f"/opt/homebrew/opt/postgresql@{version}/bin")
        if (candidate / "initdb").exists():
            return candidate
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def last_json(text: str) -> dict:
    i = text.rfind('{\n  "table"')
    if i < 0:
        i = text.rfind('{"ok"')
    return json.loads(text[i:])


def main() -> int:
    pg = find_pg_bin()
    if pg is None:
        print("psql describe schema test skipped (no PostgreSQL server binaries)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        data, home = Path(tmp) / "data", Path(tmp) / "home"
        user, port = "agentdo", free_port()
        subprocess.run([pg / "initdb", "-D", data, "-U", user, "--auth=trust"], check=True, capture_output=True)
        opts = f"-k {tmp} -p {port} -c listen_addresses=127.0.0.1"
        subprocess.run([pg / "pg_ctl", "-D", data, "-o", opts, "-l", Path(tmp) / "log", "-w", "start"],
                       check=True, capture_output=True)
        try:
            psql = [pg / "psql", "-h", "127.0.0.1", "-p", str(port), "-U", user, "-d", "postgres", "-qc"]
            subprocess.run(psql + ["create schema watcher; "
                                   "create table watcher.digest_runs(id serial primary key, note text); "
                                   "create index digest_runs_note_idx on watcher.digest_runs(note); "
                                   "create table public.plain(id int primary key);"], check=True)
            env = dict(os.environ, AGENT_DO_HOME=str(home), PATH=f"{pg}:{os.environ['PATH']}")

            def tool(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run([str(ROOT / "tools/agent-psql"), *args], env=env, text=True,
                                      capture_output=True, timeout=60)

            r = tool("connect", f"postgresql://{user}@127.0.0.1:{port}/postgres")
            if r.returncode != 0:
                raise AssertionError(f"connect failed: {r.stdout} {r.stderr}")
            r = tool("describe", "watcher.digest_runs")
            out = last_json(r.stdout)
            if not (out.get("ok") and out.get("schema") == "watcher" and len(out.get("indexes", [])) == 2):
                raise AssertionError(f"non-public describe failed: rc={r.returncode} {r.stdout[-400:]}")
            r = tool("describe", "plain")
            out = last_json(r.stdout)
            if not (out.get("ok") and out.get("schema") == "public"):
                raise AssertionError(f"public describe regressed: {r.stdout[-400:]}")
            tool("disconnect")
        finally:
            subprocess.run([pg / "pg_ctl", "-D", data, "-m", "fast", "-w", "stop"], capture_output=True)
    print("psql describe schema test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
