#!/usr/bin/env python3
"""agent-mongo backend: connection profiles, discovery, querying, safe writes."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _home() -> Path:
    """Return the agent-do state directory, re-reading env each call."""
    return Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def _profiles_path() -> Path:
    """Return path to the connection profiles JSON file."""
    return _home() / "mongo" / "connections.json"


def _load_profiles() -> dict[str, Any]:
    """Load connection profiles from disk, returning empty structure if absent or corrupt."""
    p = _profiles_path()
    if not p.exists():
        return {"profiles": {}, "default": None}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"profiles": {}, "default": None}


def _save_profiles(data: dict[str, Any]) -> None:
    """Write profiles atomically with owner-only permissions (credentials must not be world-readable)."""
    import tempfile  # noqa: PLC0415
    p = _profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(data, indent=2) + "\n").encode()
    fd, tmp = tempfile.mkstemp(dir=p.parent)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, content)
        os.close(fd)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _envelope(command: str, *, ref: str | None = None, data: Any) -> dict[str, Any]:
    """Wrap data in the standard agent-do structured output envelope."""
    result: dict[str, Any] = {"tool": "mongo", "command": command, "timestamp": _now(), "data": data}
    if ref is not None:
        result["ref"] = ref
    return result


def _print_json(payload: Any) -> None:
    """Print payload as indented JSON to stdout, serializing unknown types via str()."""
    print(json.dumps(payload, indent=2, default=str))


def _err(msg: str, code: int = 1) -> None:
    """Print an error message to stderr and exit with the given code."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def _parse_filter(raw: str | None) -> dict[str, Any]:
    """Parse a filter from JSON string or key=value shorthand."""
    if not raw:
        return {}
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            _err(f"Invalid JSON filter: {exc}")
    # key=value shorthand — supports simple scalar values
    if "=" in raw:
        key, _, val = raw.partition("=")
        # Attempt to coerce numerics/booleans
        coerced: Any = val
        if val.lower() in ("true", "false"):
            coerced = val.lower() == "true"
        else:
            try:
                coerced = int(val)
            except ValueError:
                try:
                    coerced = float(val)
                except ValueError:
                    pass
        return {key.strip(): coerced}
    _err(f"Cannot parse filter: {raw!r}. Use JSON or key=value.")
    return {}  # unreachable


def _parse_json_arg(raw: str | None, name: str) -> Any:
    """Parse a JSON argument, supporting @file syntax."""
    if not raw:
        return None
    if raw.startswith("@"):
        try:
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _err(f"Cannot read {name} file: {exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _err(f"Invalid JSON for {name}: {exc}")


def _get_uri(connection: str | None) -> tuple[str, str]:
    """Return (uri, provider) for the given profile name or env fallback."""
    # Env var takes lowest precedence — profiles win
    env_uri = os.environ.get("MONGO_CONNECTION_STRING", "")

    if connection:
        data = _load_profiles()
        profile = data["profiles"].get(connection)
        if not profile:
            _err(f"Connection profile '{connection}' not found. "
                 f"Run: agent-do mongo connections list")
        return profile["uri"], profile.get("provider", "mongodb")

    data = _load_profiles()
    default = data.get("default")
    if default and default in data["profiles"]:
        p = data["profiles"][default]
        return p["uri"], p.get("provider", "mongodb")

    if env_uri:
        return env_uri, "mongodb"

    _err("No connection specified and no default profile set.\n"
         "  agent-do mongo connections add <name> --uri <uri> --default\n"
         "  # or set MONGO_CONNECTION_STRING")
    return "", ""  # unreachable


def _connect(uri: str, provider: str) -> Any:
    """Return a connected MongoClient, with CosmosDB-appropriate TLS settings."""
    import pymongo  # noqa: PLC0415
    kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 8000}
    if provider == "cosmosdb":
        kwargs["tls"] = True
        kwargs["tlsAllowInvalidCertificates"] = False
        kwargs["retryWrites"] = False  # CosmosDB doesn't support retryWrites
    return pymongo.MongoClient(uri, **kwargs)


# ── connection management ──────────────────────────────────────────────────────

def cmd_connections(argv: list[str]) -> None:
    """Manage saved connection profiles."""
    sub = argv[0] if argv else "list"
    rest = argv[1:]

    if sub in ("list", "ls"):
        data = _load_profiles()
        profiles = data.get("profiles", {})
        default = data.get("default")
        if not profiles:
            print("No connection profiles saved.")
            print("  agent-do mongo connections add <name> --uri <uri>")
            return
        for name, p in profiles.items():
            marker = " *" if name == default else ""
            provider = p.get("provider", "mongodb")
            added = p.get("added_at", "")[:10]
            # Mask URI credentials
            uri = p.get("uri", "")
            try:
                from urllib.parse import urlparse  # noqa: PLC0415
                parsed = urlparse(uri)
                safe = uri.replace(parsed.password or "", "****") if parsed.password else uri
            except Exception:
                import re as _re  # noqa: PLC0415
                safe = _re.sub(r'://[^:@/]+:[^@/]+@', '://****:****@', uri)
            print(f"  {name}{marker}  [{provider}]  {added}  {safe}")

    elif sub == "add":
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections add <name> --uri <uri>")
        uri = ""
        provider = "mongodb"
        is_default = False
        i = 1
        while i < len(rest):
            if rest[i] == "--uri" and i + 1 < len(rest):
                uri = rest[i + 1]
                i += 2
            elif rest[i] == "--provider" and i + 1 < len(rest):
                provider = rest[i + 1]
                i += 2
            elif rest[i] == "--default":
                is_default = True
                i += 1
            else:
                i += 1
        if not uri:
            _err("--uri is required")
        data = _load_profiles()
        data["profiles"][name] = {"uri": uri, "provider": provider, "added_at": _now()}
        if is_default or not data.get("default"):
            data["default"] = name
        _save_profiles(data)
        print(f"Saved profile '{name}' [{provider}]"
              + (" (default)" if data["default"] == name else ""))

    elif sub == "remove":
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections remove <name>")
        data = _load_profiles()
        if name not in data["profiles"]:
            _err(f"Profile '{name}' not found")
        del data["profiles"][name]
        if data.get("default") == name:
            data["default"] = next(iter(data["profiles"]), None)
        _save_profiles(data)
        print(f"Removed profile '{name}'")

    elif sub == "set-default":
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections set-default <name>")
        data = _load_profiles()
        if name not in data["profiles"]:
            _err(f"Profile '{name}' not found")
        data["default"] = name
        _save_profiles(data)
        print(f"Default connection set to '{name}'")

    elif sub == "import-from-aks":
        secret = ""
        namespace = "default"
        key = "connectionString"
        profile_name = ""
        i = 0
        while i < len(rest):
            if rest[i] == "--secret" and i + 1 < len(rest):
                secret = rest[i + 1]
                i += 2
            elif rest[i] == "--namespace" and i + 1 < len(rest):
                namespace = rest[i + 1]
                i += 2
            elif rest[i] == "--key" and i + 1 < len(rest):
                key = rest[i + 1]
                i += 2
            elif rest[i] == "--profile" and i + 1 < len(rest):
                profile_name = rest[i + 1]
                i += 2
            else:
                i += 1
        if not secret:
            _err("--secret is required")
        if not profile_name:
            profile_name = secret

        import base64  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        result = subprocess.run(
            ["kubectl", "get", "secret", secret, "-n", namespace, "-o", "json"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            _err(f"kubectl failed: {result.stderr.strip()}")
        try:
            secret_obj = json.loads(result.stdout)
            encoded = secret_obj.get("data", {}).get(key, "")
            if not encoded:
                _err(f"Key '{key}' not found in secret '{secret}' (namespace: {namespace})")
            uri = base64.b64decode(encoded).decode()
        except (ValueError, KeyError) as exc:
            _err(f"Failed to decode secret: {exc}")
        data = _load_profiles()
        data["profiles"][profile_name] = {
            "uri": uri, "provider": "cosmosdb", "added_at": _now(),
            "source": f"aks:{namespace}/{secret}",
        }
        if not data.get("default"):
            data["default"] = profile_name
        _save_profiles(data)
        print(f"Imported '{profile_name}' from AKS secret {namespace}/{secret}")

    else:
        _err(f"Unknown connections subcommand: {sub}")


# ── discovery ──────────────────────────────────────────────────────────────────

def cmd_snapshot(argv: list[str]) -> None:
    """Snapshot all databases and collections with document counts."""
    connection = None
    json_mode = False
    i = 0
    while i < len(argv):
        if argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        dbs = []
        for db_name in client.list_database_names():
            if db_name in ("admin", "local", "config"):
                continue
            db = client[db_name]
            collections = []
            for coll_name in db.list_collection_names():
                try:
                    count = db[coll_name].estimated_document_count()
                except Exception:
                    count = -1
                collections.append({"name": coll_name, "estimated_count": count})
            dbs.append({"database": db_name, "collections": collections,
                        "collection_count": len(collections)})

        payload = _envelope("snapshot", data={"provider": provider, "databases": dbs,
                                               "database_count": len(dbs)})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Provider: {provider}  Databases: {len(dbs)}")
            for db_info in dbs:
                print(f"\n  {db_info['database']}  ({db_info['collection_count']} collections)")
                for c in db_info["collections"]:
                    count_str = str(c["estimated_count"]) if c["estimated_count"] >= 0 else "?"
                    print(f"    {c['name']}  ~{count_str} docs")
    finally:
        client.close()


def cmd_schema(argv: list[str]) -> None:
    """Infer schema from a sample of documents in a collection."""
    if len(argv) < 2:
        _err("Usage: schema <db> <collection> [--sample N] [--connection <name>] [--json]")
    db_name, coll_name = argv[0], argv[1]
    sample_size = 20
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--sample" and i + 1 < len(argv):
            sample_size = int(argv[i + 1])
            i += 2
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        docs = list(coll.aggregate([{"$sample": {"size": sample_size}}]))
        if not docs:
            print(f"Collection {db_name}.{coll_name} is empty.")
            return

        # Infer field types across sample
        fields: dict[str, set[str]] = {}
        def _infer(doc: dict, prefix: str = "") -> None:
            for k, v in doc.items():
                if k == "_id" and not prefix:
                    fkey = "_id"
                else:
                    fkey = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                type_name = type(v).__name__
                if type_name == "ObjectId":
                    type_name = "ObjectId"
                elif type_name == "datetime":
                    type_name = "datetime"
                fields.setdefault(fkey, set()).add(type_name)
                if isinstance(v, dict) and len(fkey.split(".")) < 4:
                    _infer(v, f"{fkey}.")

        for doc in docs:
            _infer(doc)

        schema = [{"field": f, "types": sorted(t), "nullable": "NoneType" in t}
                  for f, t in sorted(fields.items())]

        ref = f"{db_name}.{coll_name}"
        payload = _envelope("schema", ref=ref,
                            data={"sample_size": len(docs), "fields": schema})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Schema: {ref}  (sampled {len(docs)} docs)")
            print(f"  {'FIELD':<40} TYPES")
            for f in schema:
                types = ", ".join(f["types"])
                nullable = "  nullable" if f["nullable"] else ""
                print(f"  {f['field']:<40} {types}{nullable}")
    finally:
        client.close()


def cmd_indexes(argv: list[str]) -> None:
    """List indexes on a collection."""
    if len(argv) < 2:
        _err("Usage: indexes <db> <collection> [--connection <name>] [--json]")
    db_name, coll_name = argv[0], argv[1]
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        indexes = list(coll.list_indexes())
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("indexes", ref=ref, data={"indexes": indexes})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Indexes: {ref}")
            for idx in indexes:
                keys = ", ".join(f"{k}:{v}" for k, v in idx.get("key", {}).items())
                unique = "  UNIQUE" if idx.get("unique") else ""
                print(f"  {idx.get('name')}  [{keys}]{unique}")
    finally:
        client.close()


# ── querying ───────────────────────────────────────────────────────────────────

def cmd_query(argv: list[str]) -> None:
    """Find documents in a collection with optional filter, projection, sort."""
    if len(argv) < 2:
        _err("Usage: query <db> <collection> [--where <filter>] [--limit N] [--json]")
    db_name, coll_name = argv[0], argv[1]
    where_raw = None
    projection_raw = None
    sort_raw = None
    limit = 20
    skip = 0
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--where" and i + 1 < len(argv):
            where_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--projection" and i + 1 < len(argv):
            projection_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--sort" and i + 1 < len(argv):
            sort_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif argv[i] == "--skip" and i + 1 < len(argv):
            skip = int(argv[i + 1])
            i += 2
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    filt = _parse_filter(where_raw)
    projection = _parse_json_arg(projection_raw, "--projection")
    sort = _parse_json_arg(sort_raw, "--sort")

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        cursor = coll.find(filt, projection)
        if sort:
            cursor = cursor.sort(list(sort.items()))
        if skip:
            cursor = cursor.skip(skip)
        cursor = cursor.limit(limit)
        docs = [_serialize_doc(d) for d in cursor]

        ref = f"{db_name}.{coll_name}"
        payload = _envelope("query", ref=ref,
                            data={"filter": filt, "count": len(docs),
                                  "limit": limit, "documents": docs})
        if json_mode:
            _print_json(payload)
        else:
            print(f"{ref}  filter={json.dumps(filt)}  ({len(docs)} results)")
            for doc in docs:
                print(json.dumps(doc, indent=2, default=str))
                print()
    finally:
        client.close()


def cmd_count(argv: list[str]) -> None:
    """Count documents matching a filter."""
    if len(argv) < 2:
        _err("Usage: count <db> <collection> [--where <filter>] [--connection <name>]")
    db_name, coll_name = argv[0], argv[1]
    where_raw = None
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--where" and i + 1 < len(argv):
            where_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    filt = _parse_filter(where_raw)
    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        count = coll.count_documents(filt)
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("count", ref=ref, data={"filter": filt, "count": count})
        if json_mode:
            _print_json(payload)
        else:
            print(f"{ref}  filter={json.dumps(filt)}  count={count}")
    finally:
        client.close()


def cmd_aggregate(argv: list[str]) -> None:
    """Run an aggregation pipeline."""
    if len(argv) < 2:
        _err("Usage: aggregate <db> <collection> --pipeline <json-or-@file> [--json]")
    db_name, coll_name = argv[0], argv[1]
    pipeline_raw = None
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--pipeline" and i + 1 < len(argv):
            pipeline_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    if not pipeline_raw:
        _err("--pipeline is required")
    pipeline = _parse_json_arg(pipeline_raw, "--pipeline")
    if not isinstance(pipeline, list):
        _err("--pipeline must be a JSON array")

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        docs = [_serialize_doc(d) for d in coll.aggregate(pipeline)]
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("aggregate", ref=ref,
                            data={"pipeline_stages": len(pipeline),
                                  "count": len(docs), "documents": docs})
        if json_mode:
            _print_json(payload)
        else:
            print(f"{ref}  pipeline ({len(pipeline)} stages)  ({len(docs)} results)")
            for doc in docs:
                print(json.dumps(doc, indent=2, default=str))
                print()
    finally:
        client.close()


def cmd_explain(argv: list[str]) -> None:
    """Show query execution plan — useful for inspecting RU cost on CosmosDB."""
    if len(argv) < 2:
        _err("Usage: explain <db> <collection> [--where <filter>] [--connection <name>]")
    db_name, coll_name = argv[0], argv[1]
    where_raw = None
    connection = None
    i = 2
    while i < len(argv):
        if argv[i] == "--where" and i + 1 < len(argv):
            where_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        else:
            i += 1

    filt = _parse_filter(where_raw)
    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        db = client[db_name]
        plan = db.command("explain",
                          {"find": coll_name, "filter": filt},
                          verbosity="executionStats")
        _print_json(_serialize_doc(plan))
    finally:
        client.close()


# ── safe writes ────────────────────────────────────────────────────────────────

def cmd_insert(argv: list[str]) -> None:
    """Insert a document into a collection."""
    if len(argv) < 2:
        _err("Usage: insert <db> <collection> --doc <json> [--dry-run]")
    db_name, coll_name = argv[0], argv[1]
    doc_raw = None
    dry_run = False
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--doc" and i + 1 < len(argv):
            doc_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    if not doc_raw:
        _err("--doc is required")
    doc = _parse_json_arg(doc_raw, "--doc")
    if not isinstance(doc, dict):
        _err("--doc must be a JSON object")

    if dry_run:
        print(f"[dry-run] would insert into {db_name}.{coll_name}:")
        print(json.dumps(doc, indent=2, default=str))
        sys.exit(2)

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        result = client[db_name][coll_name].insert_one(doc)
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("insert", ref=ref,
                            data={"inserted_id": str(result.inserted_id)})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Inserted into {ref}  _id={result.inserted_id}")
    finally:
        client.close()


def cmd_update(argv: list[str]) -> None:
    """Update documents matching a filter."""
    if len(argv) < 2:
        _err("Usage: update <db> <collection> --where <filter> --set <updates> [--dry-run]")
    db_name, coll_name = argv[0], argv[1]
    where_raw = None
    set_raw = None
    upsert = False
    multi = False
    dry_run = False
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--where" and i + 1 < len(argv):
            where_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--set" and i + 1 < len(argv):
            set_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--upsert":
            upsert = True
            i += 1
        elif argv[i] == "--multi":
            multi = True
            i += 1
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    if not where_raw:
        _err("--where is required for update")
    if not set_raw:
        _err("--set is required for update")

    filt = _parse_filter(where_raw)
    updates = {"$set": _parse_filter(set_raw)}

    if dry_run:
        print(f"[dry-run] would update {db_name}.{coll_name}")
        print(f"  filter: {json.dumps(filt)}")
        print(f"  update: {json.dumps(updates)}")
        print(f"  multi={multi}  upsert={upsert}")
        sys.exit(2)

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        if multi:
            result = coll.update_many(filt, updates, upsert=upsert)
        else:
            result = coll.update_one(filt, updates, upsert=upsert)
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("update", ref=ref,
                            data={"matched": result.matched_count,
                                  "modified": result.modified_count,
                                  "upserted_id": str(result.upserted_id) if result.upserted_id else None})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Updated {ref}  matched={result.matched_count} modified={result.modified_count}")
    finally:
        client.close()


def cmd_delete(argv: list[str]) -> None:
    """Delete documents matching a filter. Requires --confirm or --dry-run."""
    if len(argv) < 2:
        _err("Usage: delete <db> <collection> --where <filter> --confirm [--dry-run]")
    db_name, coll_name = argv[0], argv[1]
    where_raw = None
    confirm = False
    multi = False
    dry_run = False
    connection = None
    json_mode = False
    i = 2
    while i < len(argv):
        if argv[i] == "--where" and i + 1 < len(argv):
            where_raw = argv[i + 1]
            i += 2
        elif argv[i] == "--confirm":
            confirm = True
            i += 1
        elif argv[i] == "--multi":
            multi = True
            i += 1
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1

    if not where_raw:
        _err("--where is required for delete (never delete without a filter)")

    filt = _parse_filter(where_raw)

    if dry_run:
        print(f"[dry-run] would delete from {db_name}.{coll_name}")
        print(f"  filter: {json.dumps(filt)}")
        print(f"  multi={multi}")
        sys.exit(2)

    if not confirm:
        _err("delete requires --confirm (or use --dry-run to preview)")

    uri, provider = _get_uri(connection)
    client = _connect(uri, provider)
    try:
        coll = client[db_name][coll_name]
        if multi:
            result = coll.delete_many(filt)
        else:
            result = coll.delete_one(filt)
        ref = f"{db_name}.{coll_name}"
        payload = _envelope("delete", ref=ref,
                            data={"deleted": result.deleted_count, "filter": filt})
        if json_mode:
            _print_json(payload)
        else:
            print(f"Deleted {result.deleted_count} document(s) from {ref}")
    finally:
        client.close()


# ── serialization ──────────────────────────────────────────────────────────────

def _serialize_doc(doc: Any) -> Any:
    """Recursively convert BSON types to JSON-serializable forms."""
    if isinstance(doc, dict):
        return {k: _serialize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_serialize_doc(v) for v in doc]
    # BSON ObjectId, Decimal128, etc.
    type_name = type(doc).__name__
    if type_name in ("ObjectId", "Decimal128", "Int64", "Int32"):
        return str(doc)
    if type_name == "datetime":
        return doc.isoformat().replace("+00:00", "Z")
    return doc


# ── dispatch ───────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    """Parse top-level command and dispatch to the appropriate handler."""
    if not argv:
        print("Usage: agent-do mongo <command> [args...]")
        return 0

    cmd = argv[0]
    rest = argv[1:]

    dispatch = {
        "connections": cmd_connections,
        "snapshot": cmd_snapshot,
        "schema": cmd_schema,
        "indexes": cmd_indexes,
        "query": cmd_query,
        "count": cmd_count,
        "aggregate": cmd_aggregate,
        "explain": cmd_explain,
        "insert": cmd_insert,
        "update": cmd_update,
        "delete": cmd_delete,
    }

    handler = dispatch.get(cmd)
    if not handler:
        print(f"Error: Unknown command '{cmd}'", file=sys.stderr)
        return 1

    try:
        handler(rest)
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
