# agent-mongo

MongoDB and Azure CosmosDB (MongoDB API) plugin for agent-do. Provides structured connection profile management, read-only discovery, safe writes with dry-run support, and aggregation pipelines — all designed to be called by autonomous agents without a human in the loop.

## Requirements

- Python 3.10+
- `pymongo[srv]` (`pip install "pymongo[srv]"`)
- For AKS import: `kubectl` in PATH

## Connection credentials

URIs are never stored in plain metadata files. Each profile's connection string can live in `agent-do creds` as `MONGO_CONNECTION_<PROFILE>` or in `~/.agent-do/mongo/.creds/<profile>` (mode `0o600`), inside a `0o700` directory. The metadata file (`~/.agent-do/mongo/connections.json`) holds only non-secret fields: `provider`, `added_at`, `source`.

**Resolution order at connect time:**

1. `MONGO_CONNECTION_<PROFILE>` environment variable (uppercase, hyphens → underscores)
2. `agent-do creds` entry named `MONGO_CONNECTION_<PROFILE>`
3. Per-profile creds file (`~/.agent-do/mongo/.creds/<profile>`)
4. `MONGO_CONNECTION_STRING` environment variable (fallback / default profile)

---

## Commands

### `connections` — manage saved profiles

```bash
agent-do mongo connections list
agent-do mongo connections add <name> [--stdin] [--provider mongodb|cosmosdb] [--default]
agent-do mongo connections remove <name>
agent-do mongo connections set-default <name>
agent-do mongo connections import-from-aks --secret <k8s-secret> [--namespace <ns>] [--key connectionString] [--profile <name>]
```

Profile names must match `[a-zA-Z0-9_-]` — they become filenames. AKS secret names with dots (e.g. `cosmos.connection.string`) require `--profile` to provide a valid name.

**Examples:**
```bash
printf '%s' "$MONGO_URI" | agent-do mongo connections add prod --stdin --default
printf '%s' "$COSMOS_URI" | agent-do mongo connections add cosmos-staging --stdin --provider cosmosdb
printf '%s' "$COSMOS_URI" | agent-do creds store MONGO_CONNECTION_COSMOS_STAGING --stdin
agent-do mongo connections add cosmos-staging --provider cosmosdb --default
agent-do mongo connections import-from-aks --secret cosmos-conn-str --profile cosmos-prod --namespace myapp
```

`connections add` does not accept URI values in argv. Use `--stdin` or store
`MONGO_CONNECTION_<PROFILE>` with `agent-do creds store <KEY> --stdin` first.

---

### `snapshot` — discover all databases and collections

```bash
agent-do mongo snapshot [--connection <profile>] [--json]
```

Lists all non-system databases with their collections and estimated document counts.

```bash
agent-do mongo snapshot --json
agent-do mongo snapshot --connection cosmos-prod
```

---

### `schema` — infer field types from a sample

```bash
agent-do mongo schema <db> <collection> [--sample N] [--connection <profile>] [--json]
```

Samples up to N documents (default 20) and infers field paths, types, and nullability. Handles nested documents up to 3 levels deep. Correctly handles BSON types: `ObjectId`, `datetime`, `Decimal128`, `Int64`.

```bash
agent-do mongo schema appdb events --sample 50
agent-do mongo schema mydb users --json
```

---

### `indexes` — list indexes on a collection

```bash
agent-do mongo indexes <db> <collection> [--connection <profile>] [--json]
```

```bash
agent-do mongo indexes appdb events
```

---

### `query` — find documents

```bash
agent-do mongo query <db> <collection> \
  [--where <filter>] [--projection <json>] [--sort <json>] \
  [--limit N] [--skip N] [--connection <profile>] [--json]
```

**Filter syntax** — two forms accepted:
- JSON: `--where '{"status": "active", "age": {"$gt": 18}}'`
- `key=value` shorthand: `--where status=active` (coerces `null`, `true`/`false`, integers, floats)

Default limit is 20. JSON output includes both returned `count` and `total_matching`.
Use `--limit 0` for unlimited.

```bash
agent-do mongo query appdb events --where status=active --limit 100
agent-do mongo query mydb users --where '{"role": "admin"}' --projection '{"email": 1}' --json
agent-do mongo query mydb orders --where '{"createdAt": {"$gt": "2024-01-01"}}' --sort '{"createdAt": -1}'
```

---

### `count` — count matching documents

```bash
agent-do mongo count <db> <collection> [--where <filter>] [--connection <profile>] [--json]
```

```bash
agent-do mongo count appdb events --where status=pending
```

---

### `aggregate` — run an aggregation pipeline

```bash
agent-do mongo aggregate <db> <collection> \
  --pipeline <json-array-or-@file> \
  [--confirm] [--dry-run] [--connection <profile>] [--json]
```

Pipelines containing `$out` or `$merge` stages are **destructive** (they write to other collections). These require `--confirm` to execute or `--dry-run` to preview — they will be blocked otherwise.

```bash
# Read-only pipeline
agent-do mongo aggregate appdb events \
  --pipeline '[{"$match": {"status": "active"}}, {"$group": {"_id": "$type", "count": {"$sum": 1}}}]'

# From a file
agent-do mongo aggregate mydb orders --pipeline @pipeline.json --json

# Destructive — requires --confirm
agent-do mongo aggregate mydb events --pipeline @materialize.json --confirm

# Preview destructive pipeline without running
agent-do mongo aggregate mydb events --pipeline @materialize.json --dry-run
```

---

### `explain` — show query execution plan

```bash
agent-do mongo explain <db> <collection> [--where <filter>] [--connection <profile>]
```

Runs `explain` with `executionStats` verbosity. Useful for inspecting index usage and RU cost on CosmosDB.

```bash
agent-do mongo explain appdb events --where status=active
```

---

### `insert` — insert a document

```bash
agent-do mongo insert <db> <collection> --doc <json-or-@file> [--dry-run] [--connection <profile>] [--json]
```

```bash
agent-do mongo insert mydb users --doc '{"name": "Alice", "role": "admin"}' --dry-run
agent-do mongo insert mydb users --doc @new_user.json
```

---

### `update` — update documents

```bash
agent-do mongo update <db> <collection> \
  --where <filter> --set <updates-or-@file> \
  [--multi] [--upsert] [--dry-run] [--connection <profile>] [--json]
```

Guards:
- `--where` is required — empty filter `{}` is rejected
- `--set '{}'` (empty update object) is rejected
- `--set @file` reads update fields from a JSON file
- `--multi` to update all matching documents (default: first match only)

```bash
agent-do mongo update appdb events --where status=pending --set status=processed --dry-run
agent-do mongo update mydb users --where '{"role": "admin"}' --set '{"tier": "premium"}' --multi
agent-do mongo update mydb config --where key=theme --set @config_update.json --upsert
```

---

### `delete` — delete documents

```bash
agent-do mongo delete <db> <collection> \
  --where <filter> --confirm \
  [--multi] [--dry-run] [--connection <profile>] [--json]
```

`--confirm` is required to execute. `--where` is always required — there is no "delete all" shortcut.

```bash
agent-do mongo delete mydb sessions --where '{"expiredAt": {"$lt": "2024-01-01"}}' --dry-run
agent-do mongo delete mydb sessions --where '{"expiredAt": {"$lt": "2024-01-01"}}' --confirm --multi
```

---

## Dry-run behavior

All write commands (`insert`, `update`, `delete`, destructive `aggregate`) accept `--dry-run`. When passed:

- Prints what would be executed (filter, update doc, pipeline stages)
- Exits with code `2` (the agent-do "needs clarification" signal — orchestrators should treat this as "show me first, then confirm")
- Nothing is written to the database

---

## JSON output

Every command accepts `--json` and returns a structured envelope:

```json
{
  "tool": "query",
  "ref": "appdb.events",
  "timestamp": "2026-05-20T14:00:00Z",
  "data": {
    "filter": {"status": "active"},
    "count": 5,
    "limit": 20,
    "documents": [...]
  }
}
```

---

## CosmosDB notes

Set `--provider cosmosdb` when adding a profile. The `explain` command is especially useful for CosmosDB as it surfaces RU consumption in the execution plan when the server reports it. Connection timeouts use an 8s server selection timeout.

---

## Regression test coverage

Test suite: `tests/test_mongo.py` (217 assertions, all passing). Run via:

```bash
python3 tests/test_mongo.py
# or via the full test suite:
./test.sh
```

**Covered scenarios:**

| Area | What's tested |
|------|---------------|
| Connection profiles | add, list, remove, set-default, remove-default promotion |
| Credential security | URIs stored in 0o600 creds file, not connections.json |
| Profile validation | Invalid names rejected, whitespace-only stdin URI rejected |
| AKS import | Secret decode, dot-name hint, missing `kubectl` clean error |
| Snapshot | Database/collection enumeration |
| Schema | Field path inference, nested docs, BSON types |
| Indexes | Index listing |
| Query | Filter JSON + shorthand, limit/skip/sort, projection |
| Count | Filter matching |
| Aggregate | Read pipelines, `$out`/`$merge` blocked without `--confirm` |
| Insert | `--doc` JSON + `@file`, dry-run |
| Update | `--set` inline + `@file`, empty filter guard, empty set guard, dry-run |
| Delete | `--confirm` required, empty filter guard, `--multi`, dry-run |
| Injection safety | Shell metacharacters, `$where`, universal-match operators, path traversal |
| Edge cases | `--limit 0`, negative integers, `--sample 0`, `key=null` coercion |
