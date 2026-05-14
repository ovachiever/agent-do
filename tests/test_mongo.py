#!/usr/bin/env python3
"""Integration tests for agent-mongo: connection profiles, discovery, querying, safe writes."""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
FIXTURES_DIR = ROOT / "tools" / "agent-mongo" / "fixtures"

# Fake pymongo injected via PYTHONPATH so the real one (if installed) is shadowed.
_FAKE_PYMONGO = '''
"""Fake pymongo for agent-mongo integration tests."""

FIXTURE_DOCS = [
    {"_id": "507f1f77bcf86cd799439011", "externalId": "x001",
     "status": "pending", "amount": 100.50},
    {"_id": "507f1f77bcf86cd799439012", "externalId": "x002",
     "status": "done", "amount": 200.00},
]

FIXTURE_INDEXES = [
    {"name": "_id_", "key": {"_id": 1}},
    {"name": "externalId_1", "key": {"externalId": 1}, "unique": True},
]


class _Cursor(list):
    def sort(self, key_or_list, *args, **kwargs):
        return self

    def skip(self, n):
        return _Cursor(self[n:])

    def limit(self, n):
        return _Cursor(self[:n]) if n else self


class _InsertResult:
    inserted_id = "507f1f77bcf86cd799439011"


class _UpdateResult:
    def __init__(self, matched=1, modified=1):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = None


class _DeleteResult:
    def __init__(self, deleted=1):
        self.deleted_count = deleted


class _Collection:
    def __init__(self, name):
        self.name = name

    def estimated_document_count(self):
        return 42

    def find(self, filt=None, projection=None):
        return _Cursor(list(FIXTURE_DOCS))

    def aggregate(self, pipeline):
        return iter(list(FIXTURE_DOCS))

    def insert_one(self, doc):
        return _InsertResult()

    def update_one(self, filt, updates, upsert=False):
        return _UpdateResult()

    def update_many(self, filt, updates, upsert=False):
        return _UpdateResult(matched=2, modified=2)

    def delete_one(self, filt):
        return _DeleteResult()

    def delete_many(self, filt):
        return _DeleteResult(deleted=2)

    def count_documents(self, filt=None):
        return 5

    def list_indexes(self):
        return iter(list(FIXTURE_INDEXES))


class _Database:
    def __init__(self, name):
        self.name = name

    def __getitem__(self, name):
        return _Collection(name)

    def list_collection_names(self):
        return ["expectations", "payments"]

    def command(self, cmd, spec=None, **kwargs):
        return {
            "executionStats": {
                "executionTimeMillis": 3,
                "totalDocsExamined": 2,
                "indexesUsed": ["externalId_1"],
            }
        }


class MongoClient:
    def __init__(self, uri, **kwargs):
        self.uri = uri

    def __getitem__(self, name):
        return _Database(name)

    def list_database_names(self):
        # admin/local/config should be filtered by agent-mongo
        return ["prism_bcc", "admin", "local", "config"]

    def close(self):
        pass
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_home = tmp / "agent_home"
        fake_home.mkdir()
        fake_lib = tmp / "lib"
        fake_lib.mkdir()
        fake_bin = tmp / "bin"
        fake_bin.mkdir()

        (fake_lib / "pymongo.py").write_text(_FAKE_PYMONGO)

        base_env: dict[str, str] = {
            **os.environ,
            "AGENT_DO_HOME": str(fake_home),
            "MONGO_CONNECTION_STRING": "mongodb://test:pass@localhost:27017",
            "PYTHONPATH": str(fake_lib) + (":" + os.environ["PYTHONPATH"] if "PYTHONPATH" in os.environ else ""),
            "PATH": str(fake_bin) + ":" + os.environ.get("PATH", ""),
        }

        fails = 0

        def check(label: str, cond: bool, detail: str = "") -> None:
            nonlocal fails
            if cond:
                print(f"  ok  {label}")
            else:
                print(f"FAIL  {label}" + (f": {detail}" if detail else ""))
                fails += 1

        print("\n=== agent-mongo integration tests ===\n")

        # ── connection management ──────────────────────────────────────────────
        print("--- connections ---")

        # list when empty
        r = run([str(AGENT_DO), "mongo", "connections", "list"], env=base_env)
        check("connections list (empty) exit 0", r.returncode == 0)
        check("connections list (empty) message", "No connection profiles" in r.stdout)

        # add first profile as default
        r = run(
            [str(AGENT_DO), "mongo", "connections", "add", "prism_bcc",
             "--uri", "mongodb://user:s3cr3t@cosmosdb.example.com:10255/?ssl=true",
             "--provider", "cosmosdb", "--default"],
            env=base_env,
        )
        check("connections add exit 0", r.returncode == 0, r.stderr)
        check("connections add shows name+provider", "prism_bcc" in r.stdout and "cosmosdb" in r.stdout)

        # list shows profile with masked password and default marker
        r = run([str(AGENT_DO), "mongo", "connections", "list"], env=base_env)
        check("connections list has profile", "prism_bcc" in r.stdout)
        check("connections list masks password", "s3cr3t" not in r.stdout)
        check("connections list default marker", "*" in r.stdout)

        # add second profile (non-default)
        r = run(
            [str(AGENT_DO), "mongo", "connections", "add", "dev_local",
             "--uri", "mongodb://localhost:27017"],
            env=base_env,
        )
        check("connections add second exit 0", r.returncode == 0, r.stderr)

        # set-default
        r = run([str(AGENT_DO), "mongo", "connections", "set-default", "dev_local"], env=base_env)
        check("connections set-default exit 0", r.returncode == 0, r.stderr)
        check("connections set-default message", "dev_local" in r.stdout)

        # remove second profile — default should roll back to remaining profile
        r = run([str(AGENT_DO), "mongo", "connections", "remove", "dev_local"], env=base_env)
        check("connections remove exit 0", r.returncode == 0, r.stderr)

        r = run([str(AGENT_DO), "mongo", "connections", "list"], env=base_env)
        check("connections remove rolls back default", "prism_bcc" in r.stdout)

        # import-from-aks with a fake kubectl that echoes base64-encoded URI
        aks_uri = "mongodb://cosmos:aks_secret@cosmosdb.prism.example.com:10255/?ssl=true"
        encoded = base64.b64encode(aks_uri.encode()).decode()
        make_exec(
            fake_bin / "kubectl",
            f"#!/usr/bin/env python3\nimport sys\nsys.stdout.write({encoded!r})\n",
        )

        r = run(
            [str(AGENT_DO), "mongo", "connections", "import-from-aks",
             "--secret", "cosmos-connection-string",
             "--namespace", "prism",
             "--profile", "aks_cosmos"],
            env=base_env,
        )
        check("import-from-aks exit 0", r.returncode == 0, r.stderr)
        check("import-from-aks message", "aks_cosmos" in r.stdout)

        # ── discovery ─────────────────────────────────────────────────────────
        print("\n--- discovery ---")

        # snapshot --json
        r = run([str(AGENT_DO), "mongo", "snapshot", "--json"], env=base_env)
        check("snapshot exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("snapshot tool=mongo", out["tool"] == "mongo")
        check("snapshot command=snapshot", out["command"] == "snapshot")
        dbs = out["data"]["databases"]
        check("snapshot has prism_bcc", any(d["database"] == "prism_bcc" for d in dbs))
        check("snapshot filters admin/local/config",
              all(d["database"] not in ("admin", "local", "config") for d in dbs))
        colls = [c["name"] for d in dbs for c in d["collections"]]
        check("snapshot includes expectations", "expectations" in colls)

        # snapshot human-readable
        r = run([str(AGENT_DO), "mongo", "snapshot"], env=base_env)
        check("snapshot human exit 0", r.returncode == 0, r.stderr)
        check("snapshot human output", "prism_bcc" in r.stdout)

        # schema --json
        r = run(
            [str(AGENT_DO), "mongo", "schema", "prism_bcc", "expectations", "--json"],
            env=base_env,
        )
        check("schema exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("schema command", out["command"] == "schema")
        check("schema ref", out["ref"] == "prism_bcc.expectations")
        check("schema has fields", len(out["data"]["fields"]) > 0)
        field_names = [f["field"] for f in out["data"]["fields"]]
        check("schema includes externalId", "externalId" in field_names)
        check("schema includes status", "status" in field_names)

        # indexes --json
        r = run(
            [str(AGENT_DO), "mongo", "indexes", "prism_bcc", "expectations", "--json"],
            env=base_env,
        )
        check("indexes exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("indexes command", out["command"] == "indexes")
        idx_names = [i["name"] for i in out["data"]["indexes"]]
        check("indexes has _id_", "_id_" in idx_names)
        check("indexes has externalId_1", "externalId_1" in idx_names)

        # ── querying ──────────────────────────────────────────────────────────
        print("\n--- querying ---")

        # query with key=value shorthand
        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--json"],
            env=base_env,
        )
        check("query (key=value) exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("query command", out["command"] == "query")
        check("query filter parsed", out["data"]["filter"] == {"externalId": "x001"})
        check("query returns documents", out["data"]["count"] > 0)

        # query with JSON filter and --limit
        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--where", '{"status":"pending"}', "--limit", "5", "--json"],
            env=base_env,
        )
        check("query (JSON filter) exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("query JSON filter parsed", out["data"]["filter"] == {"status": "pending"})
        check("query limit stored", out["data"]["limit"] == 5)

        # query with integer coercion
        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--where", "retries=3", "--json"],
            env=base_env,
        )
        check("query int coercion exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("query int coerced", out["data"]["filter"] == {"retries": 3})

        # count with filter
        r = run(
            [str(AGENT_DO), "mongo", "count", "prism_bcc", "expectations",
             "--where", "status=pending", "--json"],
            env=base_env,
        )
        check("count exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("count command", out["command"] == "count")
        check("count is int", isinstance(out["data"]["count"], int))

        # count without filter
        r = run(
            [str(AGENT_DO), "mongo", "count", "prism_bcc", "expectations", "--json"],
            env=base_env,
        )
        check("count (no filter) exit 0", r.returncode == 0, r.stderr)

        # aggregate with inline pipeline
        r = run(
            [str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
             "--pipeline", '[{"$count":"total"}]', "--json"],
            env=base_env,
        )
        check("aggregate exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("aggregate command", out["command"] == "aggregate")
        check("aggregate pipeline_stages=1", out["data"]["pipeline_stages"] == 1)

        # aggregate with @file pipeline
        pipeline_file = FIXTURES_DIR / "pipeline_status_counts.json"
        r = run(
            [str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
             "--pipeline", f"@{pipeline_file}", "--json"],
            env=base_env,
        )
        check("aggregate @file exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("aggregate @file pipeline_stages=2", out["data"]["pipeline_stages"] == 2)

        # explain
        r = run(
            [str(AGENT_DO), "mongo", "explain", "prism_bcc", "expectations",
             "--where", "externalId=x001"],
            env=base_env,
        )
        check("explain exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("explain has executionStats", "executionStats" in out)

        # ── safe writes ───────────────────────────────────────────────────────
        print("\n--- safe writes ---")

        # insert --dry-run
        r = run(
            [str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
             "--doc", '{"externalId":"y001","status":"pending"}', "--dry-run"],
            env=base_env,
        )
        check("insert dry-run exit 2", r.returncode == 2)
        check("insert dry-run shows [dry-run]", "[dry-run]" in r.stdout)

        # insert real (no dry-run)
        r = run(
            [str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
             "--doc", '{"externalId":"y001","status":"pending"}', "--json"],
            env=base_env,
        )
        check("insert exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("insert command", out["command"] == "insert")
        check("insert has inserted_id", "inserted_id" in out["data"])

        # update --dry-run
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--set", "status=done", "--dry-run"],
            env=base_env,
        )
        check("update dry-run exit 2", r.returncode == 2)
        check("update dry-run shows [dry-run]", "[dry-run]" in r.stdout)
        check("update dry-run shows collection", "prism_bcc.expectations" in r.stdout)

        # update real (no dry-run)
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--set", "status=done", "--json"],
            env=base_env,
        )
        check("update exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("update command", out["command"] == "update")
        check("update matched > 0", out["data"]["matched"] > 0)

        # update --multi dry-run
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "status=pending", "--set", "retries=0", "--multi", "--dry-run"],
            env=base_env,
        )
        check("update --multi dry-run exit 2", r.returncode == 2)
        check("update --multi dry-run shows multi=True", "multi=True" in r.stdout)

        # delete --dry-run
        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--dry-run"],
            env=base_env,
        )
        check("delete dry-run exit 2", r.returncode == 2)
        check("delete dry-run shows [dry-run]", "[dry-run]" in r.stdout)

        # delete with --confirm
        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--confirm", "--json"],
            env=base_env,
        )
        check("delete confirmed exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("delete command", out["command"] == "delete")
        check("delete count > 0", out["data"]["deleted"] > 0)

        # ── safety guards ─────────────────────────────────────────────────────
        print("\n--- safety guards ---")

        # delete without --confirm and without --dry-run must fail
        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
             "--where", "externalId=x001"],
            env=base_env,
        )
        check("delete no-confirm fails", r.returncode != 0)
        check("delete no-confirm mentions --confirm", "--confirm" in r.stderr)

        # delete without --where must fail
        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations", "--confirm"],
            env=base_env,
        )
        check("delete no-where fails", r.returncode != 0)

        # update without --where must fail
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--set", "status=done"],
            env=base_env,
        )
        check("update no-where fails", r.returncode != 0)

        # no connection configured and no env var
        no_conn_env = {
            **base_env,
            "MONGO_CONNECTION_STRING": "",
            "AGENT_DO_HOME": str(tmp / "empty_home"),
        }
        r = run([str(AGENT_DO), "mongo", "query", "db", "coll"], env=no_conn_env)
        check("no-connection fails", r.returncode != 0)
        check("no-connection error message", "No connection" in r.stderr)

        # invalid JSON filter
        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--where", '{"broken":json}'],
            env=base_env,
        )
        check("invalid JSON filter fails", r.returncode != 0)

        # unknown command
        r = run([str(AGENT_DO), "mongo", "notacommand"], env=base_env)
        check("unknown command fails", r.returncode != 0)

        # ── summary ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 40}")
        if fails:
            print(f"FAILED: {fails} test(s) failed")
            return 1
        print("All tests passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
