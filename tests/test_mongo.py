#!/usr/bin/env python3

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
# FIXTURE_DOCS is the canonical in-test dataset; it includes fake BSON-typed values
# (ObjectId, Decimal128, Int64, datetime) so _serialize_doc() is exercised on every
# query call.  tools/agent-mongo/fixtures/sample_documents.json is a separate
# illustrative/seed file for manual testing — it is not loaded by this test suite.
_FAKE_PYMONGO = '''
"""Fake pymongo for agent-mongo integration tests."""
from datetime import datetime

# Fake BSON types whose __name__ matches what _serialize_doc() inspects.
class ObjectId(str):
    pass

class Decimal128:
    def __init__(self, val):
        self._val = val

    def __str__(self):
        return str(self._val)

class Int64(int):
    pass

FIXTURE_DOCS = [
    {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "externalId": "x001",
        "status": "pending",
        "amount": Decimal128("100.50"),
        "createdAt": datetime(2026, 1, 15, 9, 0, 0),
        "retries": Int64(0),
        "metadata": {"source": "api", "retries": 0},
    },
    {
        "_id": ObjectId("507f1f77bcf86cd799439012"),
        "externalId": "x002",
        "status": "done",
        "amount": Decimal128("200.00"),
        "createdAt": datetime(2026, 1, 16, 12, 30, 0),
        "retries": Int64(1),
        "metadata": {"source": "batch", "retries": 1},
    },
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

        pythonpath = os.pathsep.join(filter(None, [str(fake_lib), os.environ.get("PYTHONPATH", "")]))
        base_env: dict[str, str] = {
            **os.environ,
            "AGENT_DO_HOME": str(fake_home),
            "MONGO_CONNECTION_STRING": "mongodb://test:pass@localhost:27017",
            "PYTHONPATH": pythonpath,
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
        # URI must be in creds file, not in connections.json
        conn_json = json.loads((fake_home / "mongo" / "connections.json").read_text())
        check("connections add: URI not in connections.json",
              "uri" not in conn_json["profiles"].get("prism_bcc", {}))
        check("connections add: creds file exists",
              (fake_home / "mongo" / ".creds" / "prism_bcc").exists())
        check("connections add: creds file mode is 0o600",
              stat.S_IMODE((fake_home / "mongo" / ".creds" / "prism_bcc").stat().st_mode) == 0o600)

        # list shows profile metadata; URI is never printed (stored in separate creds file)
        r = run([str(AGENT_DO), "mongo", "connections", "list"], env=base_env)
        check("connections list has profile", "prism_bcc" in r.stdout)
        check("connections list does not expose URI", "s3cr3t" not in r.stdout and "cosmosdb.example.com" not in r.stdout)
        check("connections list shows secure-store note", "stored securely" in r.stdout)
        check("connections list default marker", "*" in r.stdout)

        r = run([str(AGENT_DO), "mongo", "connections", "list", "--json"], env=base_env)
        check("connections list --json exit 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("connections list --json tool=mongo", out["tool"] == "mongo")
            check("connections list --json command=connections", out["command"] == "connections")
            check("connections list --json has profile rows", len(out["data"]["profiles"]) == 1)

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
        creds_local = fake_home / "mongo" / ".creds" / "dev_local"
        creds_local.unlink(missing_ok=True)

        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations", "--limit", "1", "--json"], env=base_env)
        check("missing default creds falls back to MONGO_CONNECTION_STRING", r.returncode == 0, r.stderr)

        r = run([str(AGENT_DO), "mongo", "connections", "remove", "dev_local"], env=base_env)
        check("connections remove exit 0", r.returncode == 0, r.stderr)

        r = run([str(AGENT_DO), "mongo", "connections", "list"], env=base_env)
        check("connections remove rolls back default", "prism_bcc" in r.stdout)

        # import-from-aks with a fake kubectl that returns -o json format.
        # mongo_ops.py now uses kubectl -o json + Python json.loads to handle
        # key names with hyphens or dots that jsonpath cannot express.
        aks_uri = "mongodb://cosmos:aks_secret@cosmosdb.prism.example.com:10255/?ssl=true"
        encoded = base64.b64encode(aks_uri.encode()).decode()
        secret_json = json.dumps({"data": {"connectionString": encoded}})
        make_exec(
            fake_bin / "kubectl",
            f"#!/usr/bin/env python3\nimport sys\nsys.stdout.write({secret_json!r})\n",
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
        # Verify URI is in the creds file, NOT in connections.json
        conn_json = json.loads((fake_home / "mongo" / "connections.json").read_text())
        check("import-from-aks: URI not in connections.json",
              "uri" not in conn_json["profiles"].get("aks_cosmos", {}))
        creds_file = fake_home / "mongo" / ".creds" / "aks_cosmos"
        check("import-from-aks: URI stored in creds file", creds_file.exists())
        check("import-from-aks: creds file mode is 0o600",
              stat.S_IMODE(creds_file.stat().st_mode) == 0o600)
        check("import-from-aks: creds file contains URI", aks_uri in creds_file.read_text())

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
        check("schema nested field uses single dot (not double)",
              "metadata.source" in field_names)
        check("schema no double-dot in any field name",
              not any(".." in f for f in field_names))

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
        # Verify _serialize_doc converts BSON types: ObjectId→str, Decimal128→str,
        # Int64→str, datetime→ISO string (all present in FIXTURE_DOCS).
        first = out["data"]["documents"][0] if out["data"]["documents"] else {}
        check("query BSON ObjectId serialized as str", isinstance(first.get("_id"), str))
        check("query BSON Decimal128 serialized as str", isinstance(first.get("amount"), str))
        check("query BSON Int64 serialized as str", isinstance(first.get("retries"), str))
        check("query datetime serialized as str", isinstance(first.get("createdAt"), str))

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

        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--where", "status=active",
             "--projection", '{"externalId": 1}',
             "--sort", '{"externalId": 1}',
             "--skip", "1",
             "--json"],
            env=base_env,
        )
        check("query metadata --json exit 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("query metadata includes projection", out["data"]["projection"] == {"externalId": 1})
            check("query metadata includes sort", out["data"]["sort"] == {"externalId": 1})
            check("query metadata includes skip", out["data"]["skip"] == 1)

        r = run(
            [str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
             "--sort", '"name"'],
            env=base_env,
        )
        check("query malformed sort fails", r.returncode != 0)
        check("query malformed sort message", "sort" in r.stderr.lower())

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

        # explain --json
        r = run(
            [str(AGENT_DO), "mongo", "explain", "prism_bcc", "expectations",
             "--where", "externalId=x001", "--json"],
            env=base_env,
        )
        check("explain exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        check("explain command=explain", out.get("command") == "explain")
        check("explain has plan.executionStats", "executionStats" in out.get("data", {}).get("plan", {}))

        # explain human-readable (no --json)
        r = run(
            [str(AGENT_DO), "mongo", "explain", "prism_bcc", "expectations",
             "--where", "externalId=x001"],
            env=base_env,
        )
        check("explain human exit 0", r.returncode == 0, r.stderr)
        check("explain human shows executionTimeMillis", "executionTimeMillis" in r.stdout)

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

        # empty filter '{}' is rejected for update and delete — even with --dry-run —
        # because '{}' matches every document and is too dangerous for an agent-facing tool.
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "{}", "--set", "status=done"],
            env=base_env,
        )
        check("update empty-filter fails", r.returncode != 0)
        check("update empty-filter error mentions document", "every document" in r.stderr)

        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "{}", "--set", "status=done", "--dry-run"],
            env=base_env,
        )
        check("update empty-filter dry-run also fails", r.returncode != 0)

        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
             "--where", "{}", "--confirm"],
            env=base_env,
        )
        check("delete empty-filter fails", r.returncode != 0)
        check("delete empty-filter error mentions document", "every document" in r.stderr)

        r = run(
            [str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
             "--where", "{}", "--dry-run"],
            env=base_env,
        )
        check("delete empty-filter dry-run also fails", r.returncode != 0)

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

        # ── filter parsing edge cases ──────────────────────────────────────────
        print("\n--- filter edge cases ---")

        # bare string (no = no {) → error
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "juststring"], env=base_env)
        check("filter bare string errors", r.returncode != 0)

        # whitespace-only --where → treated as no filter (same as omitting it)
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "   ", "--json"], env=base_env)
        check("filter whitespace-only → no filter for reads", r.returncode == 0, r.stderr)

        # whitespace --where blocked for writes (resolves to empty filter)
        r = run([str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
                 "--where", "   ", "--set", "x=y", "--dry-run"], env=base_env)
        check("filter whitespace blocked for writes", r.returncode != 0)

        # key=null → None (not string "null")
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "deletedAt=null", "--json"], env=base_env)
        check("filter key=null exits 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("filter key=null coerced to None",
                  out["data"]["filter"].get("deletedAt") is None)

        # key=NULL (case-insensitive)
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "deletedAt=NULL", "--json"], env=base_env)
        check("filter key=NULL exits 0", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("filter key=NULL coerced to None",
                  out["data"]["filter"].get("deletedAt") is None)

        # falsy filter values must pass write guard (dict is non-empty)
        r = run([str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
                 "--where", "count=0", "--set", "x=y", "--dry-run"], env=base_env)
        check("filter count=0 allowed for writes", r.returncode == 2, r.stderr)

        r = run([str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
                 "--where", "active=false", "--dry-run"], env=base_env)
        check("filter active=false allowed for writes", r.returncode == 2, r.stderr)

        # {} filter allowed for reads
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "{}", "--json"], env=base_env)
        check("query {} filter allowed for reads", r.returncode == 0, r.stderr)

        r = run([str(AGENT_DO), "mongo", "count", "prism_bcc", "expectations",
                 "--where", "{}", "--json"], env=base_env)
        check("count {} filter allowed for reads", r.returncode == 0, r.stderr)

        # ── numeric arg validation ─────────────────────────────────────────────
        print("\n--- numeric arg validation ---")

        # non-numeric --limit → clean error (not raw Python ValueError)
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--limit", "abc"], env=base_env)
        check("--limit non-numeric fails", r.returncode != 0)
        check("--limit non-numeric gives clear error", "--limit" in r.stderr, r.stderr.strip())

        # non-numeric --skip
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--skip", "abc"], env=base_env)
        check("--skip non-numeric fails", r.returncode != 0)
        check("--skip non-numeric gives clear error", "--skip" in r.stderr, r.stderr.strip())

        # non-numeric --sample
        r = run([str(AGENT_DO), "mongo", "schema", "prism_bcc", "expectations",
                 "--sample", "abc"], env=base_env)
        check("--sample non-numeric fails", r.returncode != 0)
        check("--sample non-numeric gives clear error", "--sample" in r.stderr, r.stderr.strip())

        # negative --limit
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--limit", "-1"], env=base_env)
        check("--limit -1 rejected", r.returncode != 0)

        # negative --skip
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--skip", "-1"], env=base_env)
        check("--skip -1 rejected", r.returncode != 0)

        # --sample 0 rejected (MongoDB $sample requires size >= 1)
        r = run([str(AGENT_DO), "mongo", "schema", "prism_bcc", "expectations",
                 "--sample", "0"], env=base_env)
        check("--sample 0 rejected", r.returncode != 0)

        # --sample negative rejected
        r = run([str(AGENT_DO), "mongo", "schema", "prism_bcc", "expectations",
                 "--sample", "-5"], env=base_env)
        check("--sample negative rejected", r.returncode != 0)

        # ── projection / sort validation ───────────────────────────────────────
        print("\n--- projection / sort ---")

        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--projection", "notjson"], env=base_env)
        check("--projection invalid JSON fails", r.returncode != 0)

        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--sort", "notjson"], env=base_env)
        check("--sort invalid JSON fails", r.returncode != 0)

        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--projection", '{"_id":0,"externalId":1}',
                 "--sort", '{"createdAt":-1}', "--json"], env=base_env)
        check("valid projection+sort exits 0", r.returncode == 0, r.stderr)

        # ── aggregate edge cases ───────────────────────────────────────────────
        print("\n--- aggregate edge cases ---")

        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", "[]", "--json"], env=base_env)
        check("aggregate empty pipeline [] exits 0", r.returncode == 0, r.stderr)

        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", "{}"], env=base_env)
        check("aggregate pipeline {} (not array) fails", r.returncode != 0)

        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", "@/nonexistent/path.json"], env=base_env)
        check("aggregate @nonexistent file fails", r.returncode != 0)

        # ── insert edge cases ──────────────────────────────────────────────────
        print("\n--- insert edge cases ---")

        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", "[]"], env=base_env)
        check("insert --doc array fails", r.returncode != 0)

        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", "null"], env=base_env)
        check("insert --doc null fails", r.returncode != 0)

        # empty doc {} is valid MongoDB — allowed
        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", "{}", "--json"], env=base_env)
        check("insert empty doc {} allowed", r.returncode == 0, r.stderr)

        # ── injection / operator security ─────────────────────────────────────
        print("\n--- injection ---")

        # Shell metacharacters in --where value: passed as a single Python string,
        # never interpreted by a shell. The semicolon, backtick, and $() are literals.
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", "status=done; echo INJECTED", "--json"], env=base_env)
        check("shell metacharacters (semicolon) in key=value: parsed as literal string",
              r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("shell metacharacters: filter value is literal (not executed)",
                  out["data"]["filter"].get("status") == "done; echo INJECTED")

        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", '{"cmd": "$(rm -rf /)"}', "--dry-run"], env=base_env)
        check("$() in --doc JSON value treated as literal (dry-run)", r.returncode == 2)
        check("$() in --doc not executed (dry-run output present)", "[dry-run]" in r.stdout)

        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", 'externalId=`id`', "--json"], env=base_env)
        check("backtick in key=value: parsed as literal string", r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("backtick value is literal (not executed)",
                  out["data"]["filter"].get("externalId") == "`id`")

        # $where JavaScript operator: passes through to pymongo (server-side concern).
        # agent-mongo does NOT execute JavaScript locally — it passes the filter as a BSON
        # dict to pymongo which sends it to the MongoDB server. JS execution on the server
        # depends on the server's security settings (noScripting option).
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--where", '{"$where": "function() { return true; }"}', "--json"],
                env=base_env)
        check("$where JS operator passes through to pymongo (not executed locally)",
              r.returncode == 0, r.stderr)
        if r.returncode == 0:
            out = json.loads(r.stdout)
            check("$where filter passed to pymongo verbatim",
                  "$where" in out["data"]["filter"])

        # Universal-match operators ($exists, $ne: null) on write operations:
        # These pass the empty-filter guard (the dict is non-empty) — this is EXPECTED.
        # The guard catches accidental {} only. Explicit operators require the caller to
        # use --dry-run to verify scope first, and --confirm for delete.
        r = run([str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
                 "--where", '{"_id": {"$exists": true}}', "--set", "status=reviewed",
                 "--multi", "--dry-run"], env=base_env)
        check("universal-match op ($exists:true) passes filter guard, dry-run shows scope",
              r.returncode == 2)
        check("dry-run output contains filter",
              "$exists" in r.stdout or "reviewed" in r.stdout)

        r = run([str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
                 "--where", '{"status": {"$ne": null}}', "--dry-run"], env=base_env)
        check("$ne:null on delete shows dry-run scope (--confirm still required to execute)",
              r.returncode == 2)

        # $out stage in aggregate: BLOCKED without --confirm (fixed gap).
        # Previously, aggregate had no confirmation requirement even for destructive stages.
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$out": "archive"}]'], env=base_env)
        check("aggregate $out blocked without --confirm", r.returncode != 0)
        check("aggregate $out error mentions --confirm or destructive", "confirm" in r.stderr.lower())

        # $out with an object argument (cross-database write)
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$out": {"db": "other", "coll": "victims"}}]'],
                env=base_env)
        check("aggregate $out (object form) blocked without --confirm", r.returncode != 0)

        # $merge stage: also destructive
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$group": {"_id": "$status"}}, {"$merge": {"into": "summaries"}}]'],
                env=base_env)
        check("aggregate $merge stage blocked without --confirm", r.returncode != 0)
        check("aggregate $merge error mentions --confirm or destructive", "confirm" in r.stderr.lower())

        # $out allowed with --confirm
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$out": "archive"}]', "--confirm", "--json"],
                env=base_env)
        check("aggregate $out allowed with --confirm", r.returncode == 0, r.stderr)

        # $out allowed with --dry-run (previews without executing)
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$out": "archive"}]', "--dry-run"], env=base_env)
        check("aggregate $out dry-run exits 2", r.returncode == 2)
        check("aggregate $out dry-run shows [dry-run]", "[dry-run]" in r.stdout)
        check("aggregate $out dry-run shows stage name", "$out" in r.stdout)

        # Normal aggregate (no destructive stages) still works without --confirm
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$count": "total"}]', "--json"], env=base_env)
        check("aggregate without destructive stages needs no --confirm", r.returncode == 0, r.stderr)

        # @file path traversal: reading non-JSON system files fails cleanly.
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", "@/etc/passwd"], env=base_env)
        check("@/etc/passwd as --pipeline fails cleanly (not valid JSON array)", r.returncode != 0)

        # /dev/null is empty — _parse_json_arg errors on empty JSON
        r = run([str(AGENT_DO), "mongo", "query", "prism_bcc", "expectations",
                 "--projection", "@/dev/null"], env=base_env)
        check("@/dev/null as --projection fails gracefully", r.returncode != 0)

        # @file with a valid JSON file (connections.json) as --pipeline must still fail
        # the array type check (connections.json is an object, not an array).
        conn_file = fake_home / "mongo" / "connections.json"
        if conn_file.exists():
            r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                     "--pipeline", f"@{conn_file}"], env=base_env)
            check("@connections.json as --pipeline blocked (object, not array)", r.returncode != 0)

        # Profile names are now used as filenames in the creds store.
        # Path-traversal characters (slashes, dots-dot) must be rejected upfront.
        r = run([str(AGENT_DO), "mongo", "connections", "add", "../../../etc/shadow",
                 "--uri", "mongodb://localhost:27017"], env=base_env)
        check("profile name with path traversal chars rejected (not stored as file path)",
              r.returncode != 0)
        check("profile name rejection error is clear", "Invalid profile name" in r.stderr)

        # Names with spaces or special chars also rejected
        r = run([str(AGENT_DO), "mongo", "connections", "add", "bad name!",
                 "--uri", "mongodb://localhost:27017"], env=base_env)
        check("profile name with space/special chars rejected", r.returncode != 0)

        # import-from-aks with a secret name that contains dots — should error with
        # a hint to pass --profile rather than the generic "Invalid profile name" message.
        r = run(
            [str(AGENT_DO), "mongo", "connections", "import-from-aks",
             "--secret", "cosmos.connection.string",
             "--namespace", "prism"],
            env=base_env,
        )
        check("import-from-aks dotted secret name rejected with hint", r.returncode != 0)
        check("import-from-aks dot hint mentions --profile", "--profile" in r.stderr)

        # --set @file on update: verify file-based JSON update payloads are accepted.
        # Write a small update payload to a temp file and use it via --set @path.
        set_file = tmp / "update_payload.json"
        set_file.write_text(json.dumps({"status": "archived", "score": 99}))
        r = run(
            [str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
             "--where", "status=active",
             "--set", f"@{set_file}",
             "--dry-run"],
            env=base_env,
        )
        check("update --set @file dry-run exits 2", r.returncode == 2)
        check("update --set @file dry-run shows field", "archived" in r.stdout or "archived" in r.stderr)

        # --set '{}' (empty object) must be rejected — it would be a silent no-op
        r = run([str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
                 "--where", "status=active", "--set", "{}"], env=base_env)
        check("update --set '{}' empty object rejected", r.returncode != 0)
        check("update --set '{}' error is clear", "field" in r.stderr.lower() or "empty" in r.stderr.lower())

        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", '{"x": 1}', "--dry-runx"], env=base_env)
        check("insert mistyped flag is rejected", r.returncode != 0)
        check("insert mistyped flag error is clear", "Unknown argument" in r.stderr)

        # --uri with whitespace only must be rejected — not stored as garbage creds
        r = run([str(AGENT_DO), "mongo", "connections", "add", "wstest",
                 "--uri", "   "], env=base_env)
        check("connections add whitespace-only --uri rejected", r.returncode != 0)

        r = run(
            [str(AGENT_DO), "mongo", "connections", "add", "badprovider",
             "--uri", "mongodb://localhost:27017", "--provider", "not-a-real-provider"],
            env=base_env,
        )
        check("connections add invalid provider rejected", r.returncode != 0)
        check("connections add invalid provider message", "provider" in r.stderr.lower())

        # import-from-aks when kubectl not installed gives clean error (not unhandled exception).
        # Inject a fake kubectl that exits 127 (command not found) to simulate missing binary
        # while keeping python3 and agent-do reachable.
        make_exec(fake_bin / "kubectl",
                  "#!/bin/sh\necho 'kubectl: command not found' >&2\nexit 127\n")
        r = run([str(AGENT_DO), "mongo", "connections", "import-from-aks",
                 "--secret", "my-secret", "--namespace", "default", "--profile", "myprofile"],
                env=base_env)
        check("import-from-aks missing kubectl gives clean error", r.returncode != 0)
        check("import-from-aks missing kubectl error is readable",
              "kubectl" in r.stderr.lower() or "failed" in r.stderr.lower())
        # clean up fake kubectl so it doesn't affect other tests
        (fake_bin / "kubectl").unlink(missing_ok=True)

        # ── dry-run --json output is valid JSON, not plain text ───────────────
        print("\n--- dry-run --json output ---")

        r = run([str(AGENT_DO), "mongo", "insert", "prism_bcc", "expectations",
                 "--doc", '{"x":1}', "--dry-run", "--json"], env=base_env)
        check("insert dry-run --json exits 2", r.returncode == 2)
        drj = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
        check("insert dry-run --json is valid JSON", drj is not None, r.stdout[:200])
        check("insert dry-run --json has dry_run=true", (drj or {}).get("dry_run") is True)

        r = run([str(AGENT_DO), "mongo", "update", "prism_bcc", "expectations",
                 "--where", "x=1", "--set", "y=2", "--dry-run", "--json"], env=base_env)
        check("update dry-run --json exits 2", r.returncode == 2)
        drj = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
        check("update dry-run --json is valid JSON", drj is not None, r.stdout[:200])
        check("update dry-run --json has dry_run=true", (drj or {}).get("dry_run") is True)

        r = run([str(AGENT_DO), "mongo", "delete", "prism_bcc", "expectations",
                 "--where", "x=1", "--dry-run", "--json"], env=base_env)
        check("delete dry-run --json exits 2", r.returncode == 2)
        drj = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
        check("delete dry-run --json is valid JSON", drj is not None, r.stdout[:200])
        check("delete dry-run --json has dry_run=true", (drj or {}).get("dry_run") is True)

        # aggregate --dry-run for non-destructive pipeline: must preview and exit 2
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$count":"total"}]', "--dry-run"], env=base_env)
        check("aggregate non-destructive --dry-run exits 2", r.returncode == 2)
        check("aggregate non-destructive --dry-run shows [dry-run]", "[dry-run]" in r.stdout)

        # aggregate --dry-run --json for non-destructive pipeline
        r = run([str(AGENT_DO), "mongo", "aggregate", "prism_bcc", "expectations",
                 "--pipeline", '[{"$count":"total"}]', "--dry-run", "--json"], env=base_env)
        check("aggregate non-destructive --dry-run --json exits 2", r.returncode == 2)
        drj = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
        check("aggregate non-destructive --dry-run --json is valid JSON", drj is not None, r.stdout[:200])
        check("aggregate non-destructive --dry-run --json has dry_run=true", (drj or {}).get("dry_run") is True)

        # ── summary ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 40}")
        if fails:
            print(f"FAILED: {fails} test(s) failed")
            return 1
        print("All tests passed.")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
