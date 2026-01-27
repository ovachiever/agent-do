"""Pattern caching for agent-do."""

import os
import json
import sqlite3
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def get_cache_path() -> Path:
    """Get path to cache database."""
    cache_dir = AGENT_DO_HOME / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "patterns.db"


def init_db() -> sqlite3.Connection:
    """Initialize cache database."""
    db_path = get_cache_path()
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            intent TEXT PRIMARY KEY,
            result TEXT NOT NULL,
            hits INTEGER DEFAULT 1,
            last_used TEXT,
            created TEXT
        )
    """)
    conn.commit()
    return conn


def normalize(intent: str) -> str:
    """Normalize intent for matching."""
    # Lowercase
    text = intent.lower()
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Remove punctuation except apostrophes in contractions
    text = re.sub(r"[^\w\s']", '', text)
    # Remove common filler words
    fillers = {'please', 'can', 'you', 'would', 'could', 'the', 'a', 'an', 'to', 'for', 'me', 'my', 'i', 'want'}
    words = [w for w in text.split() if w not in fillers]
    return ' '.join(words)


def check_cache(intent: str) -> Optional[dict]:
    """Check if we've seen a similar intent before."""
    conn = init_db()
    normalized = normalize(intent)

    cursor = conn.execute(
        "SELECT result FROM patterns WHERE intent = ?",
        (normalized,)
    )
    row = cursor.fetchone()

    if row:
        # Update hit count and last used
        conn.execute(
            "UPDATE patterns SET hits = hits + 1, last_used = ? WHERE intent = ?",
            (datetime.now().isoformat(), normalized)
        )
        conn.commit()
        conn.close()
        return json.loads(row[0])

    conn.close()
    return None


def cache_result(intent: str, result: dict) -> None:
    """Cache successful routing for future use."""
    conn = init_db()
    normalized = normalize(intent)
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT OR REPLACE INTO patterns (intent, result, hits, last_used, created)
        VALUES (?, ?, COALESCE((SELECT hits FROM patterns WHERE intent = ?), 0) + 1, ?,
                COALESCE((SELECT created FROM patterns WHERE intent = ?), ?))
    """, (normalized, json.dumps(result), normalized, now, normalized, now))
    conn.commit()
    conn.close()


def get_all_patterns() -> list:
    """Get all cached patterns."""
    conn = init_db()
    cursor = conn.execute(
        "SELECT intent, result, hits, last_used FROM patterns ORDER BY hits DESC"
    )
    patterns = []
    for row in cursor:
        patterns.append({
            'intent': row[0],
            'result': json.loads(row[1]),
            'hits': row[2],
            'last_used': row[3]
        })
    conn.close()
    return patterns


def clear_cache() -> None:
    """Clear all cached patterns."""
    conn = init_db()
    conn.execute("DELETE FROM patterns")
    conn.commit()
    conn.close()


def fuzzy_match(intent: str, threshold: float = 0.6) -> Optional[dict]:
    """Try to find a fuzzy match in cache."""
    normalized = normalize(intent)
    words = set(normalized.split())

    if not words:
        return None

    conn = init_db()
    cursor = conn.execute("SELECT intent, result FROM patterns")

    best_match = None
    best_score = 0.0

    for row in cursor:
        cached_intent = row[0]
        cached_words = set(cached_intent.split())

        if not cached_words:
            continue

        # Jaccard similarity
        intersection = len(words & cached_words)
        union = len(words | cached_words)
        score = intersection / union if union > 0 else 0

        if score > best_score and score >= threshold:
            best_score = score
            best_match = json.loads(row[1])

    conn.close()
    return best_match
