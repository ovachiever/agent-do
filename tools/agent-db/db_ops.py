#!/usr/bin/env python3
"""
agent-db v2 - AI-first database exploration and querying.
See the schema, understand the shape, then act.
"""

import json
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path
from difflib import get_close_matches
from typing import Any, Optional

# Database drivers - imported on demand
def get_postgres_connection(host, port, database, user, password):
    import psycopg2
    return psycopg2.connect(host=host, port=port, database=database, user=user, password=password)

def get_mysql_connection(host, port, database, user, password):
    import pymysql
    return pymysql.connect(host=host, port=int(port), database=database, user=user, password=password)

def get_mssql_connection(host, port, database, user, password):
    try:
        import pymssql
        return pymssql.connect(server=host, port=str(port), database=database, user=user, password=password)
    except ImportError:
        import pyodbc
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password}"
        return pyodbc.connect(conn_str)

def get_sqlite_connection(database, **kwargs):
    import sqlite3
    return sqlite3.connect(database)


class DatabaseSession:
    """Manages database connection and session state."""
    
    CONFIG_DIR = Path.home() / '.agent-db'
    PROFILES_FILE = CONFIG_DIR / 'profiles.json'
    SESSION_FILE = CONFIG_DIR / 'session.json'
    
    def __init__(self):
        self.CONFIG_DIR.mkdir(exist_ok=True)
        self.connection = None
        self.cursor = None
        self.db_type = None
        self.profile_name = None
        self.database_name = None
        self.in_transaction = False
        self.history = []
        self._load_session()
    
    def _load_session(self):
        """Load session state from file."""
        if self.SESSION_FILE.exists():
            try:
                data = json.loads(self.SESSION_FILE.read_text())
                self.profile_name = data.get('profile')
                self.database_name = data.get('database')
                self.db_type = data.get('db_type')
                self.in_transaction = data.get('in_transaction', False)
                self.history = data.get('history', [])[-50:]  # Keep last 50
            except:
                pass
    
    def _save_session(self):
        """Save session state to file."""
        data = {
            'profile': self.profile_name,
            'database': self.database_name,
            'db_type': self.db_type,
            'connected_at': datetime.now().isoformat(),
            'in_transaction': self.in_transaction,
            'history': self.history[-50:]
        }
        self.SESSION_FILE.write_text(json.dumps(data, indent=2))
    
    def _clear_session(self):
        """Clear session state."""
        if self.SESSION_FILE.exists():
            self.SESSION_FILE.unlink()
        self.connection = None
        self.cursor = None
        self.profile_name = None
        self.database_name = None
        self.in_transaction = False
    
    def _load_profiles(self) -> dict:
        """Load connection profiles."""
        if self.PROFILES_FILE.exists():
            return json.loads(self.PROFILES_FILE.read_text())
        return {}
    
    def _save_profiles(self, profiles: dict):
        """Save connection profiles."""
        self.PROFILES_FILE.write_text(json.dumps(profiles, indent=2))
    
    def _get_password(self, profile_name: str) -> Optional[str]:
        """Get password from keychain or environment."""
        # Check environment first
        env_key = f"AGENT_DB_PASSWORD_{profile_name.upper().replace('-', '_')}"
        if env_key in os.environ:
            return os.environ[env_key]
        
        # Try macOS keychain
        if sys.platform == 'darwin':
            try:
                result = subprocess.run(
                    ['security', 'find-generic-password', '-a', profile_name, '-s', 'agent-db', '-w'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except:
                pass
        
        return None
    
    def _store_password(self, profile_name: str, password: str):
        """Store password in keychain."""
        if sys.platform == 'darwin':
            try:
                # Delete existing
                subprocess.run(
                    ['security', 'delete-generic-password', '-a', profile_name, '-s', 'agent-db'],
                    capture_output=True
                )
                # Add new
                subprocess.run(
                    ['security', 'add-generic-password', '-a', profile_name, '-s', 'agent-db', '-w', password],
                    capture_output=True
                )
            except:
                pass
    
    def _get_connection(self):
        """Get or create database connection."""
        if self.connection:
            return self.connection
        
        if not self.profile_name:
            return None
        
        profiles = self._load_profiles()
        if self.profile_name not in profiles:
            return None
        
        profile = profiles[self.profile_name]
        password = self._get_password(self.profile_name)
        
        self.db_type = profile.get('type', 'postgres')
        
        connectors = {
            'postgres': get_postgres_connection,
            'postgresql': get_postgres_connection,
            'pg': get_postgres_connection,
            'mysql': get_mysql_connection,
            'mariadb': get_mysql_connection,
            'mssql': get_mssql_connection,
            'sqlserver': get_mssql_connection,
            'sqlite': get_sqlite_connection,
        }
        
        connector = connectors.get(self.db_type)
        if not connector:
            raise ValueError(f"Unknown database type: {self.db_type}")
        
        self.connection = connector(
            host=profile.get('host', 'localhost'),
            port=profile.get('port', self._default_port()),
            database=profile.get('database'),
            user=profile.get('user'),
            password=password
        )
        self.database_name = profile.get('database')
        return self.connection
    
    def _default_port(self):
        """Get default port for database type."""
        return {
            'postgres': 5432, 'postgresql': 5432, 'pg': 5432,
            'mysql': 3306, 'mariadb': 3306,
            'mssql': 1433, 'sqlserver': 1433,
            'sqlite': None
        }.get(self.db_type, 5432)
    
    def _add_to_history(self, sql: str, row_count: int):
        """Add query to history."""
        self.history.append({
            'sql': sql[:500],  # Truncate long queries
            'at': datetime.now().isoformat(),
            'rows': row_count
        })
        self._save_session()
    
    def _get_table_names(self) -> list:
        """Get all table names for fuzzy matching."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type in ('postgres', 'postgresql', 'pg'):
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        elif self.db_type in ('mysql', 'mariadb'):
            cursor.execute("SHOW TABLES")
        elif self.db_type in ('mssql', 'sqlserver'):
            cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        elif self.db_type == 'sqlite':
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        
        return [row[0] for row in cursor.fetchall()]
    
    def _suggest_table(self, name: str) -> Optional[str]:
        """Suggest similar table name."""
        tables = self._get_table_names()
        matches = get_close_matches(name.lower(), [t.lower() for t in tables], n=3, cutoff=0.4)
        if matches:
            # Return original case
            for t in tables:
                if t.lower() in matches:
                    return t
        return None
    
    # ==================== Commands ====================
    
    def cmd_connect(self, profile_or_conn: str) -> dict:
        """Connect to database."""
        try:
            # Check if it's a connection string
            if '://' in profile_or_conn:
                # Parse connection string
                # Format: type://user:pass@host:port/database
                return {"ok": False, "error": "Connection strings not yet implemented. Use profile name."}
            
            profiles = self._load_profiles()
            if profile_or_conn not in profiles:
                return {
                    "ok": False,
                    "error": f"Profile '{profile_or_conn}' not found",
                    "suggestion": f"Available profiles: {list(profiles.keys())}. Use 'agent-db profile add {profile_or_conn}' to create.",
                    "exit_code": 1
                }
            
            self.profile_name = profile_or_conn
            conn = self._get_connection()
            
            if conn:
                self._save_session()
                return {
                    "ok": True,
                    "message": f"Connected to {self.database_name}",
                    "database": self.database_name,
                    "type": self.db_type,
                    "profile": self.profile_name
                }
            else:
                return {"ok": False, "error": "Failed to connect", "exit_code": 1}
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 1}
    
    def cmd_disconnect(self) -> dict:
        """Disconnect from database."""
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        self._clear_session()
        return {"ok": True, "message": "Disconnected"}
    
    def cmd_status(self) -> dict:
        """Show connection status."""
        if self.profile_name:
            return {
                "ok": True,
                "connected": True,
                "profile": self.profile_name,
                "database": self.database_name,
                "type": self.db_type,
                "in_transaction": self.in_transaction
            }
        else:
            return {
                "ok": True,
                "connected": False,
                "message": "Not connected. Use 'agent-db connect <profile>' to connect."
            }
    
    def cmd_profiles(self) -> dict:
        """List connection profiles."""
        profiles = self._load_profiles()
        return {
            "ok": True,
            "profiles": [
                {
                    "name": name,
                    "type": p.get('type'),
                    "host": p.get('host'),
                    "database": p.get('database'),
                    "user": p.get('user')
                }
                for name, p in profiles.items()
            ]
        }
    
    def cmd_profile_add(self, name: str, db_type: str, host: str, port: int, 
                        database: str, user: str, password: str = None) -> dict:
        """Add a connection profile."""
        profiles = self._load_profiles()
        
        profiles[name] = {
            'type': db_type,
            'host': host,
            'port': port,
            'database': database,
            'user': user
        }
        
        self._save_profiles(profiles)
        
        if password:
            self._store_password(name, password)
        
        return {
            "ok": True,
            "message": f"Profile '{name}' added",
            "note": "Password stored in keychain" if password else "Set password via AGENT_DB_PASSWORD_{NAME} env var"
        }
    
    def cmd_profile_remove(self, name: str) -> dict:
        """Remove a connection profile."""
        profiles = self._load_profiles()
        
        if name not in profiles:
            return {"ok": False, "error": f"Profile '{name}' not found", "exit_code": 1}
        
        del profiles[name]
        self._save_profiles(profiles)
        
        return {"ok": True, "message": f"Profile '{name}' removed"}
    
    def cmd_snapshot(self, tables_only: bool = False, compact: bool = False) -> dict:
        """Get schema overview."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            tables = []
            
            # Get tables
            if self.db_type in ('postgres', 'postgresql', 'pg'):
                cursor.execute("""
                    SELECT t.tablename, 
                           (SELECT reltuples::bigint FROM pg_class WHERE relname = t.tablename) as row_count
                    FROM pg_tables t 
                    WHERE t.schemaname = 'public'
                    ORDER BY t.tablename
                """)
                table_rows = cursor.fetchall()
                
                for table_name, row_count in table_rows:
                    if compact:
                        tables.append(table_name)
                    elif tables_only:
                        tables.append({"name": table_name, "rows": row_count or 0})
                    else:
                        # Get columns
                        cursor.execute("""
                            SELECT column_name, data_type, is_nullable, column_default
                            FROM information_schema.columns 
                            WHERE table_name = %s AND table_schema = 'public'
                            ORDER BY ordinal_position
                        """, (table_name,))
                        columns = []
                        for col in cursor.fetchall():
                            columns.append({
                                "name": col[0],
                                "type": col[1],
                                "nullable": col[2] == 'YES'
                            })
                        
                        # Get primary key
                        cursor.execute("""
                            SELECT a.attname
                            FROM pg_index i
                            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                            WHERE i.indrelid = %s::regclass AND i.indisprimary
                        """, (table_name,))
                        pk_cols = [row[0] for row in cursor.fetchall()]
                        
                        for col in columns:
                            if col['name'] in pk_cols:
                                col['key'] = 'PK'
                        
                        tables.append({
                            "name": table_name,
                            "rows": row_count or 0,
                            "columns": columns
                        })
            
            elif self.db_type in ('mysql', 'mariadb'):
                cursor.execute("SHOW TABLES")
                table_names = [row[0] for row in cursor.fetchall()]
                
                for table_name in table_names:
                    if compact:
                        tables.append(table_name)
                    else:
                        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                        row_count = cursor.fetchone()[0]
                        
                        if tables_only:
                            tables.append({"name": table_name, "rows": row_count})
                        else:
                            cursor.execute(f"DESCRIBE `{table_name}`")
                            columns = []
                            for col in cursor.fetchall():
                                columns.append({
                                    "name": col[0],
                                    "type": col[1],
                                    "nullable": col[2] == 'YES',
                                    "key": 'PK' if col[3] == 'PRI' else ('FK' if col[3] == 'MUL' else None)
                                })
                            tables.append({
                                "name": table_name,
                                "rows": row_count,
                                "columns": columns
                            })
            
            elif self.db_type in ('mssql', 'sqlserver'):
                cursor.execute("""
                    SELECT t.TABLE_NAME,
                           (SELECT SUM(p.rows) FROM sys.partitions p 
                            JOIN sys.tables tb ON p.object_id = tb.object_id 
                            WHERE tb.name = t.TABLE_NAME AND p.index_id IN (0,1)) as row_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE t.TABLE_TYPE = 'BASE TABLE'
                    ORDER BY t.TABLE_NAME
                """)
                table_rows = cursor.fetchall()
                
                for table_name, row_count in table_rows:
                    if compact:
                        tables.append(table_name)
                    elif tables_only:
                        tables.append({"name": table_name, "rows": row_count or 0})
                    else:
                        cursor.execute("""
                            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
                            FROM INFORMATION_SCHEMA.COLUMNS
                            WHERE TABLE_NAME = ?
                            ORDER BY ORDINAL_POSITION
                        """, (table_name,))
                        columns = []
                        for col in cursor.fetchall():
                            col_type = col[1]
                            if col[3]:
                                col_type += f"({col[3]})"
                            columns.append({
                                "name": col[0],
                                "type": col_type,
                                "nullable": col[2] == 'YES'
                            })
                        tables.append({
                            "name": table_name,
                            "rows": row_count or 0,
                            "columns": columns
                        })
            
            elif self.db_type == 'sqlite':
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                table_names = [row[0] for row in cursor.fetchall()]
                
                for table_name in table_names:
                    if compact:
                        tables.append(table_name)
                    else:
                        cursor.execute(f"SELECT COUNT(*) FROM '{table_name}'")
                        row_count = cursor.fetchone()[0]
                        
                        if tables_only:
                            tables.append({"name": table_name, "rows": row_count})
                        else:
                            cursor.execute(f"PRAGMA table_info('{table_name}')")
                            columns = []
                            for col in cursor.fetchall():
                                columns.append({
                                    "name": col[1],
                                    "type": col[2],
                                    "nullable": col[3] == 0,
                                    "key": 'PK' if col[5] else None
                                })
                            tables.append({
                                "name": table_name,
                                "rows": row_count,
                                "columns": columns
                            })
            
            result = {
                "ok": True,
                "database": self.database_name,
                "type": self.db_type,
                "table_count": len(tables)
            }
            
            if compact:
                result["tables"] = tables
            else:
                result["tables"] = tables
            
            return result
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}
    
    def cmd_tables(self, pattern: str = None) -> dict:
        """List tables."""
        result = self.cmd_snapshot(tables_only=True)
        if not result.get("ok"):
            return result
        
        tables = result.get("tables", [])
        if pattern:
            tables = [t for t in tables if pattern.lower() in t.get("name", "").lower()]
        
        return {
            "ok": True,
            "tables": tables,
            "count": len(tables)
        }
    
    def cmd_describe(self, table: str) -> dict:
        """Describe table schema in detail."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            
            # Check if table exists
            tables = self._get_table_names()
            if table not in tables:
                suggestion = self._suggest_table(table)
                return {
                    "ok": False,
                    "error": f"Table '{table}' does not exist",
                    "suggestion": f"Did you mean '{suggestion}'?" if suggestion else "Use 'agent-db tables' to list all tables.",
                    "exit_code": 3
                }
            
            result = {
                "ok": True,
                "table": table,
                "columns": [],
                "primary_key": [],
                "foreign_keys": [],
                "referenced_by": [],
                "indexes": []
            }
            
            if self.db_type in ('postgres', 'postgresql', 'pg'):
                # Columns
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable, column_default, character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table,))
                for col in cursor.fetchall():
                    col_type = col[1]
                    if col[4]:
                        col_type += f"({col[4]})"
                    result["columns"].append({
                        "name": col[0],
                        "type": col_type,
                        "nullable": col[2] == 'YES',
                        "default": col[3]
                    })
                
                # Primary key
                cursor.execute("""
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = %s::regclass AND i.indisprimary
                """, (table,))
                result["primary_key"] = [row[0] for row in cursor.fetchall()]
                
                # Foreign keys
                cursor.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table,
                        ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
                """, (table,))
                for fk in cursor.fetchall():
                    result["foreign_keys"].append({
                        "column": fk[0],
                        "references": f"{fk[1]}.{fk[2]}"
                    })
                
                # Referenced by
                cursor.execute("""
                    SELECT
                        tc.table_name,
                        kcu.column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = %s
                """, (table,))
                for ref in cursor.fetchall():
                    result["referenced_by"].append({
                        "table": ref[0],
                        "column": ref[1]
                    })
                
                # Indexes
                cursor.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = %s
                """, (table,))
                for idx in cursor.fetchall():
                    result["indexes"].append({
                        "name": idx[0],
                        "definition": idx[1]
                    })
            
            # Similar implementations for MySQL, MSSQL, SQLite...
            # (abbreviated for length)
            
            return result
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}
    
    def cmd_sample(self, table: str, n: int = 5, random: bool = False) -> dict:
        """Sample rows from table."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            
            # Check if table exists
            tables = self._get_table_names()
            if table not in tables:
                suggestion = self._suggest_table(table)
                return {
                    "ok": False,
                    "error": f"Table '{table}' does not exist",
                    "suggestion": f"Did you mean '{suggestion}'?" if suggestion else None,
                    "exit_code": 3
                }
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            total = cursor.fetchone()[0]
            
            # Sample query
            if self.db_type in ('postgres', 'postgresql', 'pg'):
                if random:
                    cursor.execute(f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT %s", (n,))
                else:
                    cursor.execute(f"SELECT * FROM {table} LIMIT %s", (n,))
            elif self.db_type in ('mysql', 'mariadb'):
                if random:
                    cursor.execute(f"SELECT * FROM `{table}` ORDER BY RAND() LIMIT %s", (n,))
                else:
                    cursor.execute(f"SELECT * FROM `{table}` LIMIT %s", (n,))
            elif self.db_type in ('mssql', 'sqlserver'):
                if random:
                    cursor.execute(f"SELECT TOP {n} * FROM [{table}] ORDER BY NEWID()")
                else:
                    cursor.execute(f"SELECT TOP {n} * FROM [{table}]")
            elif self.db_type == 'sqlite':
                if random:
                    cursor.execute(f"SELECT * FROM '{table}' ORDER BY RANDOM() LIMIT ?", (n,))
                else:
                    cursor.execute(f"SELECT * FROM '{table}' LIMIT ?", (n,))
            
            columns = [desc[0] for desc in cursor.description]
            rows = [list(row) for row in cursor.fetchall()]
            
            # Convert non-JSON-serializable types
            for row in rows:
                for i, val in enumerate(row):
                    if isinstance(val, (datetime,)):
                        row[i] = val.isoformat()
                    elif isinstance(val, bytes):
                        row[i] = val.hex()
                    elif val is not None and not isinstance(val, (str, int, float, bool, list, dict)):
                        row[i] = str(val)
            
            return {
                "ok": True,
                "table": table,
                "columns": columns,
                "rows": rows,
                "sampled": len(rows),
                "total_rows": total
            }
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}
    
    def cmd_count(self, table: str) -> dict:
        """Get row count for table."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            return {"ok": True, "table": table, "count": count}
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}
    
    def cmd_query(self, sql: str, limit: int = None, explain: bool = False) -> dict:
        """Execute SQL query."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            start_time = time.time()
            
            # Add EXPLAIN if requested
            if explain:
                if self.db_type in ('postgres', 'postgresql', 'pg'):
                    sql = f"EXPLAIN ANALYZE {sql}"
                elif self.db_type in ('mysql', 'mariadb'):
                    sql = f"EXPLAIN {sql}"
                elif self.db_type in ('mssql', 'sqlserver'):
                    cursor.execute("SET SHOWPLAN_TEXT ON")
            
            # Add limit if not present and requested
            if limit and 'LIMIT' not in sql.upper() and 'TOP' not in sql.upper():
                if self.db_type in ('mssql', 'sqlserver'):
                    sql = sql.replace('SELECT', f'SELECT TOP {limit}', 1)
                else:
                    sql = f"{sql} LIMIT {limit}"
            
            cursor.execute(sql)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Check if it's a SELECT query
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = [list(row) for row in cursor.fetchall()]
                
                # Convert non-JSON-serializable types
                for row in rows:
                    for i, val in enumerate(row):
                        if isinstance(val, (datetime,)):
                            row[i] = val.isoformat()
                        elif isinstance(val, bytes):
                            row[i] = val.hex()
                        elif val is not None and not isinstance(val, (str, int, float, bool, list, dict)):
                            row[i] = str(val)
                
                self._add_to_history(sql, len(rows))
                
                return {
                    "ok": True,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "execution_time_ms": execution_time
                }
            else:
                # Non-SELECT query
                affected = cursor.rowcount
                if not self.in_transaction:
                    conn.commit()
                
                self._add_to_history(sql, affected)
                
                return {
                    "ok": True,
                    "affected_rows": affected,
                    "execution_time_ms": execution_time
                }
        
        except Exception as e:
            error_msg = str(e)
            result = {"ok": False, "error": error_msg, "exit_code": 4}
            
            # Try to provide helpful suggestions
            if 'does not exist' in error_msg.lower() or 'invalid object' in error_msg.lower():
                # Try to extract table name and suggest
                result["exit_code"] = 3
                result["suggestion"] = "Use 'agent-db tables' to see available tables."
            
            return result
    
    def cmd_export(self, sql: str, filename: str, format: str = None) -> dict:
        """Export query results to file."""
        result = self.cmd_query(sql)
        if not result.get("ok"):
            return result
        
        # Determine format from extension
        if not format:
            if filename.endswith('.json'):
                format = 'json'
            elif filename.endswith('.xlsx'):
                format = 'excel'
            else:
                format = 'csv'
        
        try:
            if format == 'json':
                with open(filename, 'w') as f:
                    json.dump({
                        "columns": result["columns"],
                        "rows": result["rows"]
                    }, f, indent=2)
            
            elif format == 'csv':
                import csv
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(result["columns"])
                    writer.writerows(result["rows"])
            
            elif format == 'excel':
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(result["columns"])
                for row in result["rows"]:
                    ws.append(row)
                wb.save(filename)
            
            return {
                "ok": True,
                "file": filename,
                "format": format,
                "rows": result["row_count"]
            }
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}
    
    def cmd_history(self, last: bool = False) -> dict:
        """Show query history."""
        if last and self.history:
            return {
                "ok": True,
                "last_query": self.history[-1]
            }
        
        return {
            "ok": True,
            "history": self.history
        }
    
    def cmd_begin(self) -> dict:
        """Begin transaction."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            if self.in_transaction:
                return {"ok": False, "error": "Already in transaction", "exit_code": 7}
            
            # Most drivers auto-begin, just mark state
            self.in_transaction = True
            self._save_session()
            
            return {"ok": True, "message": "Transaction started"}
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 7}
    
    def cmd_commit(self) -> dict:
        """Commit transaction."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            if not self.in_transaction:
                return {"ok": False, "error": "No active transaction", "exit_code": 7}
            
            conn.commit()
            self.in_transaction = False
            self._save_session()
            
            return {"ok": True, "message": "Transaction committed"}
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 7}
    
    def cmd_rollback(self) -> dict:
        """Rollback transaction."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            if not self.in_transaction:
                return {"ok": False, "error": "No active transaction", "exit_code": 7}
            
            conn.rollback()
            self.in_transaction = False
            self._save_session()
            
            return {"ok": True, "message": "Transaction rolled back"}
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 7}
    
    def cmd_relations(self, table: str = None) -> dict:
        """Show foreign key relationships."""
        try:
            conn = self._get_connection()
            if not conn:
                return {"ok": False, "error": "Not connected", "exit_code": 1}
            
            cursor = conn.cursor()
            relations = []
            
            if self.db_type in ('postgres', 'postgresql', 'pg'):
                sql = """
                    SELECT
                        tc.table_name as from_table,
                        kcu.column_name as from_column,
                        ccu.table_name AS to_table,
                        ccu.column_name AS to_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                """
                if table:
                    sql += f" AND (tc.table_name = '{table}' OR ccu.table_name = '{table}')"
                
                cursor.execute(sql)
                for row in cursor.fetchall():
                    relations.append({
                        "from": f"{row[0]}.{row[1]}",
                        "to": f"{row[2]}.{row[3]}",
                        "type": "many-to-one"
                    })
            
            return {
                "ok": True,
                "relations": relations,
                "count": len(relations)
            }
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 8}


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI-first database tool')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # connect
    p = subparsers.add_parser('connect', help='Connect to database')
    p.add_argument('profile', help='Profile name or connection string')
    
    # disconnect
    subparsers.add_parser('disconnect', help='Disconnect from database')
    
    # status
    subparsers.add_parser('status', help='Show connection status')
    
    # profiles
    subparsers.add_parser('profiles', help='List connection profiles')
    
    # profile add
    p = subparsers.add_parser('profile', help='Profile management')
    p.add_argument('action', choices=['add', 'remove'])
    p.add_argument('name', help='Profile name')
    p.add_argument('--type', help='Database type (postgres, mysql, mssql, sqlite)')
    p.add_argument('--host', help='Database host')
    p.add_argument('--port', type=int, help='Database port')
    p.add_argument('--database', help='Database name')
    p.add_argument('--user', help='Username')
    p.add_argument('--password', help='Password (stored in keychain)')
    
    # snapshot
    p = subparsers.add_parser('snapshot', help='Schema overview')
    p.add_argument('--tables', action='store_true', help='Tables only')
    p.add_argument('--compact', action='store_true', help='Minimal output')
    
    # tables
    p = subparsers.add_parser('tables', help='List tables')
    p.add_argument('pattern', nargs='?', help='Filter pattern')
    
    # describe
    p = subparsers.add_parser('describe', help='Describe table')
    p.add_argument('table', help='Table name')
    
    # sample
    p = subparsers.add_parser('sample', help='Sample rows')
    p.add_argument('table', help='Table name')
    p.add_argument('n', nargs='?', type=int, default=5, help='Number of rows')
    p.add_argument('--random', action='store_true', help='Random sample')
    
    # count
    p = subparsers.add_parser('count', help='Count rows')
    p.add_argument('table', help='Table name')
    
    # query
    p = subparsers.add_parser('query', help='Execute SQL')
    p.add_argument('sql', help='SQL query')
    p.add_argument('--limit', type=int, help='Limit rows')
    p.add_argument('--explain', action='store_true', help='Show execution plan')
    
    # export
    p = subparsers.add_parser('export', help='Export to file')
    p.add_argument('sql', help='SQL query')
    p.add_argument('file', help='Output file')
    p.add_argument('--format', choices=['csv', 'json', 'excel'], help='Output format')
    
    # history
    p = subparsers.add_parser('history', help='Query history')
    p.add_argument('--last', action='store_true', help='Show last query only')
    
    # begin/commit/rollback
    subparsers.add_parser('begin', help='Begin transaction')
    subparsers.add_parser('commit', help='Commit transaction')
    subparsers.add_parser('rollback', help='Rollback transaction')
    
    # relations
    p = subparsers.add_parser('relations', help='Show FK relationships')
    p.add_argument('table', nargs='?', help='Table name (optional)')
    
    args = parser.parse_args()
    
    session = DatabaseSession()
    result = {"ok": False, "error": "Unknown command"}
    
    if args.command == 'connect':
        result = session.cmd_connect(args.profile)
    elif args.command == 'disconnect':
        result = session.cmd_disconnect()
    elif args.command == 'status':
        result = session.cmd_status()
    elif args.command == 'profiles':
        result = session.cmd_profiles()
    elif args.command == 'profile':
        if args.action == 'add':
            result = session.cmd_profile_add(
                args.name, args.type, args.host, args.port,
                args.database, args.user, args.password
            )
        elif args.action == 'remove':
            result = session.cmd_profile_remove(args.name)
    elif args.command == 'snapshot':
        result = session.cmd_snapshot(tables_only=args.tables, compact=args.compact)
    elif args.command == 'tables':
        result = session.cmd_tables(args.pattern)
    elif args.command == 'describe':
        result = session.cmd_describe(args.table)
    elif args.command == 'sample':
        result = session.cmd_sample(args.table, args.n, args.random)
    elif args.command == 'count':
        result = session.cmd_count(args.table)
    elif args.command == 'query':
        result = session.cmd_query(args.sql, args.limit, args.explain)
    elif args.command == 'export':
        result = session.cmd_export(args.sql, args.file, args.format)
    elif args.command == 'history':
        result = session.cmd_history(args.last)
    elif args.command == 'begin':
        result = session.cmd_begin()
    elif args.command == 'commit':
        result = session.cmd_commit()
    elif args.command == 'rollback':
        result = session.cmd_rollback()
    elif args.command == 'relations':
        result = session.cmd_relations(args.table)
    elif args.command is None:
        parser.print_help()
        sys.exit(0)
    
    print(json.dumps(result, indent=2, default=str))
    sys.exit(result.get('exit_code', 0) if not result.get('ok') else 0)


if __name__ == '__main__':
    main()
