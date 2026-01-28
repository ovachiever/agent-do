# agent-db v2 Specification

> AI-first database exploration and querying. See the schema, understand the shape, then act.

## Philosophy

The same pattern that makes agent-excel work:

```
CONNECT → SNAPSHOT → EXPLORE → QUERY → VERIFY
```

**Key insight:** Databases are too large to snapshot data, but you CAN snapshot the **schema** - which is what AI needs to write correct queries.

## Core Commands

### Connection Management

```bash
agent-db connect <profile|connection-string>    # Establish session
agent-db disconnect                             # End session
agent-db status                                 # Show current connection
agent-db profiles                               # List saved profiles
agent-db profile add <name>                     # Add new profile (interactive)
agent-db profile remove <name>                  # Remove profile
```

### Schema Exploration (The "Snapshot" Equivalent)

```bash
agent-db snapshot                    # Full schema overview
agent-db snapshot --tables           # Tables only (names + row counts)
agent-db snapshot --compact          # Minimal: just table names
agent-db tables [pattern]            # List tables matching pattern
agent-db describe <table>            # Detailed table schema
agent-db relations                   # FK relationship map
agent-db relations <table>           # Relations for specific table
```

### Data Sampling (Peek Without Loading Everything)

```bash
agent-db sample <table> [n]          # Sample n rows (default: 5)
agent-db sample <table> --random     # Random sample (not just TOP n)
agent-db count <table>               # Row count
agent-db stats <table>               # Column statistics (nulls, uniques, min/max)
```

### Query Execution

```bash
agent-db query "<sql>"               # Run query, return results
agent-db query "<sql>" --explain     # Show execution plan
agent-db query "<sql>" --limit 100   # Override/add LIMIT
agent-db export "<sql>" <file>       # Export to CSV/JSON/Excel
agent-db history                     # Recent queries this session
agent-db history --last              # Re-run last query
```

### Transaction Safety (For Modifications)

```bash
agent-db begin                       # Start transaction
agent-db commit                      # Commit transaction
agent-db rollback                    # Rollback transaction
agent-db status                      # Shows if in transaction
```

## Output Format

All commands return JSON for AI parsing:

### snapshot
```json
{
  "ok": true,
  "database": "SalesDB",
  "type": "mssql",
  "tables": [
    {
      "name": "customers",
      "schema": "dbo",
      "rows": 45230,
      "columns": [
        {"name": "id", "type": "int", "nullable": false, "key": "PK"},
        {"name": "name", "type": "varchar(100)", "nullable": false},
        {"name": "email", "type": "varchar(255)", "nullable": true},
        {"name": "created_at", "type": "datetime", "nullable": false}
      ]
    },
    {
      "name": "orders",
      "schema": "dbo", 
      "rows": 128445,
      "columns": [
        {"name": "id", "type": "int", "nullable": false, "key": "PK"},
        {"name": "customer_id", "type": "int", "nullable": false, "key": "FK→customers.id"},
        {"name": "total", "type": "decimal(10,2)", "nullable": false},
        {"name": "status", "type": "varchar(20)", "nullable": false}
      ]
    }
  ],
  "relationships": [
    {"from": "orders.customer_id", "to": "customers.id", "type": "many-to-one"}
  ]
}
```

### sample
```json
{
  "ok": true,
  "table": "customers",
  "columns": ["id", "name", "email", "created_at"],
  "types": ["int", "varchar", "varchar", "datetime"],
  "rows": [
    [1, "Acme Corp", "contact@acme.com", "2024-01-15 09:30:00"],
    [2, "Globex Inc", "info@globex.com", "2024-01-16 14:22:00"],
    [3, "Initech", "hello@initech.com", "2024-01-17 11:45:00"]
  ],
  "total_rows": 45230,
  "sampled": 3
}
```

### query
```json
{
  "ok": true,
  "columns": ["name", "total_orders", "total_spent"],
  "types": ["varchar", "int", "decimal"],
  "rows": [
    ["Acme Corp", 47, 12500.00],
    ["Globex Inc", 23, 8750.50]
  ],
  "row_count": 2,
  "execution_time_ms": 45
}
```

### Error Response
```json
{
  "ok": false,
  "error": "Table 'users' does not exist",
  "suggestion": "Did you mean 'customers'? Use 'agent-db tables' to see available tables.",
  "exit_code": 3
}
```

## Connection Profiles

Stored in `~/.agent-db/profiles.json` (credentials in OS keychain):

```json
{
  "prod-sales": {
    "type": "mssql",
    "host": "sql.company.com",
    "port": 1433,
    "database": "SalesDB",
    "user": "readonly"
  },
  "local-pg": {
    "type": "postgres",
    "host": "localhost",
    "port": 5432,
    "database": "devdb"
  }
}
```

Credentials stored securely:
- macOS: Keychain (`security` command)
- Linux: `secret-tool` or encrypted file
- Env override: `AGENT_DB_PASSWORD_<PROFILE>`

## Supported Databases

| Type | Connection String | Python Driver |
|------|-------------------|---------------|
| `postgres` | `postgresql://user:pass@host/db` | `psycopg2` |
| `mysql` | `mysql://user:pass@host/db` | `pymysql` |
| `mssql` | `mssql://user:pass@host/db` | `pymssql` or `pyodbc` |
| `sqlite` | `/path/to/file.db` | `sqlite3` (builtin) |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Connection failed |
| 2 | Authentication failed |
| 3 | Object not found (table, column) |
| 4 | Query syntax error |
| 5 | Permission denied |
| 6 | Timeout |
| 7 | Transaction error |
| 8 | Unknown error |

## Session State

State persisted in `~/.agent-db/session.json`:

```json
{
  "profile": "prod-sales",
  "connected_at": "2024-01-28T14:30:00Z",
  "database": "SalesDB",
  "in_transaction": false,
  "history": [
    {"sql": "SELECT * FROM customers LIMIT 5", "at": "2024-01-28T14:31:00Z", "rows": 5},
    {"sql": "SELECT COUNT(*) FROM orders", "at": "2024-01-28T14:32:00Z", "rows": 1}
  ]
}
```

## Example Workflow

```bash
# 1. Connect
agent-db connect prod-sales

# 2. Explore schema (AI sees the landscape)
agent-db snapshot
# → AI now knows: tables are customers, orders, products, order_items

# 3. Understand a specific table
agent-db describe orders
# → AI sees: columns, types, PKs, FKs, indexes

# 4. Peek at data
agent-db sample orders 5
# → AI sees actual data shape and values

# 5. Query with confidence
agent-db query "SELECT c.name, COUNT(o.id) as order_count 
                FROM customers c 
                JOIN orders o ON o.customer_id = c.id 
                GROUP BY c.name 
                ORDER BY order_count DESC 
                LIMIT 10"

# 6. Export results
agent-db export "SELECT * FROM orders WHERE status = 'pending'" pending_orders.csv

# 7. Disconnect
agent-db disconnect
```

## AI-Friendly Features

### Smart Error Messages
```bash
agent-db query "SELECT * FROM users"
```
```json
{
  "ok": false,
  "error": "Table 'users' does not exist",
  "suggestion": "Similar tables: 'customers', 'user_accounts'. Run 'agent-db tables' to list all.",
  "exit_code": 3
}
```

### Schema Hints in Query Results
```bash
agent-db query "SELECT * FROM customers LIMIT 1"
```
```json
{
  "ok": true,
  "columns": ["id", "name", "email", "created_at"],
  "types": ["int", "varchar(100)", "varchar(255)", "datetime"],
  "nullable": [false, false, true, false],
  "rows": [[1, "Acme Corp", "contact@acme.com", "2024-01-15 09:30:00"]],
  "row_count": 1
}
```

### Relation-Aware Describe
```bash
agent-db describe orders
```
```json
{
  "ok": true,
  "table": "orders",
  "columns": [...],
  "primary_key": ["id"],
  "foreign_keys": [
    {"column": "customer_id", "references": "customers.id"}
  ],
  "referenced_by": [
    {"table": "order_items", "column": "order_id"}
  ],
  "indexes": [
    {"name": "idx_orders_status", "columns": ["status"]}
  ]
}
```

## Implementation Notes

### Architecture
```
agent-db (bash CLI)
    ↓
db_ops.py (Python module)
    ↓
Database drivers (psycopg2, pymysql, pymssql, sqlite3)
```

### Why Python (not pure bash)?
- Consistent JSON output formatting
- Connection pooling / session management
- Cross-database abstraction
- Secure credential handling
- Rich error messages with suggestions

### Dependencies
```
psycopg2-binary   # PostgreSQL
pymysql           # MySQL/MariaDB  
pymssql           # SQL Server (pure Python, easy install)
# OR pyodbc       # SQL Server (requires ODBC driver)
```

## Future Enhancements

- `agent-db diff <table> --since "1 hour ago"` - Show recent changes
- `agent-db explain <sql>` - Visual execution plan
- `agent-db suggest <table>` - Suggest useful queries based on schema
- `agent-db backup <table> <file>` - Quick table backup
- `agent-db restore <table> <file>` - Restore from backup
- PowerBI integration via `agent-db powerbi refresh <dataset>`
