"""Pattern caching and route-quality memory for agent-do."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
PROJECT_MARKERS = (
    ".git",
    "CLAUDE.md",
    "AGENTS.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "pnpm-workspace.yaml",
    "turbo.json",
)


def get_cache_path() -> Path:
    """Get path to cache database."""
    cache_dir = AGENT_DO_HOME / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "patterns.db"


def normalize(intent: str) -> str:
    """Normalize intent for matching."""
    text = intent.lower()
    text = " ".join(text.split())
    text = re.sub(r"[^\w\s']", "", text)
    fillers = {"please", "can", "you", "would", "could", "the", "a", "an", "to", "for", "me", "my", "i", "want"}
    words = [word for word in text.split() if word not in fillers]
    return " ".join(words)


def infer_project_scope(cwd: str | None = None) -> str:
    """Infer the current project root for project-scoped routing memory."""
    start = Path(cwd or os.getcwd()).resolve()
    current = start

    while current != current.parent:
        for marker in PROJECT_MARKERS:
            if (current / marker).exists():
                return str(current)
        current = current.parent

    return ""


def init_db() -> sqlite3.Connection:
    """Initialize the cache database and migrate legacy schema if needed."""
    db_path = get_cache_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(patterns)")}
    if columns and "cache_key" not in columns:
        conn.execute("ALTER TABLE patterns RENAME TO patterns_legacy")
        columns = set()

    if not columns:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patterns (
                cache_key TEXT PRIMARY KEY,
                intent TEXT NOT NULL,
                project_scope TEXT DEFAULT '',
                result TEXT NOT NULL,
                hits INTEGER DEFAULT 0,
                executions INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                failures INTEGER DEFAULT 0,
                route_source TEXT DEFAULT 'unknown',
                last_used TEXT,
                last_success TEXT,
                last_failure TEXT,
                created TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_patterns_intent_scope ON patterns(intent, project_scope)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_patterns_scope_success ON patterns(project_scope, successes DESC)"
        )

        legacy_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='patterns_legacy'"
        ).fetchone()
        if legacy_exists:
            now = datetime.now().isoformat()
            rows = conn.execute(
                "SELECT intent, result, hits, last_used, created FROM patterns_legacy"
            ).fetchall()
            for row in rows:
                intent = row["intent"]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO patterns (
                        cache_key, intent, project_scope, result, hits, executions,
                        successes, failures, route_source, last_used, last_success,
                        last_failure, created
                    ) VALUES (?, ?, '', ?, ?, ?, ?, 0, 'legacy', ?, ?, NULL, ?)
                    """,
                    (
                        make_cache_key(intent, ""),
                        intent,
                        row["result"],
                        row["hits"] or 0,
                        row["hits"] or 0,
                        row["hits"] or 0,
                        row["last_used"] or now,
                        row["last_used"] or now,
                        row["created"] or now,
                    ),
                )
            conn.execute("DROP TABLE patterns_legacy")

    conn.commit()
    return conn


def make_cache_key(normalized_intent: str, project_scope: str | None = None) -> str:
    scope = project_scope or ""
    return f"{scope}::{normalized_intent}"


def _row_to_pattern(row: sqlite3.Row) -> dict:
    pattern = {
        "intent": row["intent"],
        "project_scope": row["project_scope"],
        "result": json.loads(row["result"]),
        "hits": row["hits"],
        "executions": row["executions"],
        "successes": row["successes"],
        "failures": row["failures"],
        "route_source": row["route_source"],
        "last_used": row["last_used"],
        "last_success": row["last_success"],
        "last_failure": row["last_failure"],
        "created": row["created"],
    }
    return pattern


def _candidate_rows(conn: sqlite3.Connection, normalized: str, project_scope: str | None) -> list[sqlite3.Row]:
    scope = project_scope or ""
    if scope:
        return conn.execute(
            """
            SELECT * FROM patterns
            WHERE intent = ? AND project_scope IN (?, '')
            ORDER BY CASE WHEN project_scope = ? THEN 0 ELSE 1 END, successes DESC, hits DESC
            """,
            (normalized, scope, scope),
        ).fetchall()

    return conn.execute(
        "SELECT * FROM patterns WHERE intent = ? AND project_scope = '' ORDER BY successes DESC, hits DESC",
        (normalized,),
    ).fetchall()


def check_cache(intent: str, project_scope: str | None = None) -> Optional[dict]:
    """Check for an exact cached route, preferring project-scoped matches."""
    conn = init_db()
    normalized = normalize(intent)
    rows = _candidate_rows(conn, normalized, project_scope)
    row = rows[0] if rows else None

    if row:
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE patterns SET hits = hits + 1, last_used = ? WHERE cache_key = ?",
            (now, row["cache_key"]),
        )
        conn.commit()
        conn.close()
        return json.loads(row["result"])

    conn.close()
    return None


def cache_result(intent: str, result: dict, project_scope: str | None = None, route_source: str = "unknown") -> None:
    """Persist a candidate route for future use, scoped to the current project when available."""
    conn = init_db()
    normalized = normalize(intent)
    scope = project_scope or ""
    now = datetime.now().isoformat()
    cache_key = make_cache_key(normalized, scope)

    existing = conn.execute(
        "SELECT hits, executions, successes, failures, created FROM patterns WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()

    hits = existing["hits"] if existing else 0
    executions = existing["executions"] if existing else 0
    successes = existing["successes"] if existing else 0
    failures = existing["failures"] if existing else 0
    created = existing["created"] if existing else now

    conn.execute(
        """
        INSERT OR REPLACE INTO patterns (
            cache_key, intent, project_scope, result, hits, executions,
            successes, failures, route_source, last_used, last_success,
            last_failure, created
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            COALESCE((SELECT last_success FROM patterns WHERE cache_key = ?), NULL),
            COALESCE((SELECT last_failure FROM patterns WHERE cache_key = ?), NULL),
            ?)
        """,
        (
            cache_key,
            normalized,
            scope,
            json.dumps(result),
            hits,
            executions,
            successes,
            failures,
            route_source,
            now,
            cache_key,
            cache_key,
            created,
        ),
    )
    conn.commit()
    conn.close()


def note_route_outcome(
    intent: str,
    result: dict,
    success: bool,
    project_scope: str | None = None,
    route_source: str = "unknown",
) -> None:
    """Record whether a cached or freshly-routed command executed successfully."""
    conn = init_db()
    normalized = normalize(intent)
    scope = project_scope or ""
    now = datetime.now().isoformat()
    cache_key = make_cache_key(normalized, scope)

    existing = conn.execute(
        "SELECT * FROM patterns WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()

    if existing is None and scope:
        fallback_key = make_cache_key(normalized, "")
        existing = conn.execute(
            "SELECT * FROM patterns WHERE cache_key = ?",
            (fallback_key,),
        ).fetchone()
        if existing is not None:
            cache_key = fallback_key
            scope = ""

    if existing is None:
        cache_result(intent, result, scope, route_source=route_source)
        existing = conn.execute(
            "SELECT * FROM patterns WHERE cache_key = ?",
            (make_cache_key(normalized, scope),),
        ).fetchone()
        if existing is None:
            conn.close()
            return
        cache_key = existing["cache_key"]

    successes = existing["successes"] + (1 if success else 0)
    failures = existing["failures"] + (0 if success else 1)
    executions = existing["executions"] + 1

    conn.execute(
        """
        UPDATE patterns
        SET executions = ?, successes = ?, failures = ?, route_source = ?, last_used = ?,
            last_success = CASE WHEN ? THEN ? ELSE last_success END,
            last_failure = CASE WHEN ? THEN last_failure ELSE ? END
        WHERE cache_key = ?
        """,
        (
            executions,
            successes,
            failures,
            route_source,
            now,
            1 if success else 0,
            now,
            1 if success else 0,
            now,
            cache_key,
        ),
    )
    conn.commit()
    conn.close()


def get_all_patterns() -> list[dict]:
    """Get all cached routes ordered by recent utility."""
    conn = init_db()
    rows = conn.execute(
        """
        SELECT * FROM patterns
        ORDER BY project_scope DESC, successes DESC, hits DESC, last_used DESC
        """
    ).fetchall()
    patterns = [_row_to_pattern(row) for row in rows]
    conn.close()
    return patterns


def clear_cache() -> None:
    """Clear all cached routes."""
    conn = init_db()
    conn.execute("DELETE FROM patterns")
    conn.commit()
    conn.close()


def fuzzy_match(intent: str, threshold: float = 0.6, project_scope: str | None = None) -> Optional[dict]:
    """Find the best fuzzy match, weighted by project scope and route quality."""
    normalized = normalize(intent)
    words = set(normalized.split())

    if not words:
        return None

    conn = init_db()
    scope = project_scope or ""
    if scope:
        rows = conn.execute(
            "SELECT * FROM patterns WHERE project_scope IN (?, '')",
            (scope,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM patterns WHERE project_scope = ''",
        ).fetchall()

    best_match = None
    best_score = 0.0

    for row in rows:
        cached_words = set((row["intent"] or "").split())
        if not cached_words:
            continue

        intersection = len(words & cached_words)
        union = len(words | cached_words)
        lexical_score = intersection / union if union > 0 else 0.0
        if lexical_score < threshold:
            continue

        project_bonus = 0.18 if scope and row["project_scope"] == scope else 0.0
        success_bonus = 0.0
        if row["executions"] > 0:
            success_rate = row["successes"] / row["executions"]
            success_bonus += (success_rate - 0.5) * 0.3
        success_bonus += min(row["successes"], 10) * 0.01
        failure_penalty = min(row["failures"], 10) * 0.02
        hit_bonus = min(row["hits"], 20) * 0.005

        weighted_score = lexical_score + project_bonus + success_bonus + hit_bonus - failure_penalty

        if weighted_score > best_score:
            best_score = weighted_score
            best_match = json.loads(row["result"])

    conn.close()
    return best_match
