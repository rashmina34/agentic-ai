# agents/v0_2_0/memory.py
"""
Persistent memory via SQLite.

Two tables:
  - memories : key/value facts the agent stores explicitly
  - summaries: compressed conversation summaries (for context sliding window)

Design: plain SQL, no ORM, easy to inspect with any SQLite browser.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import MEMORY_DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL,
                tags      TEXT DEFAULT '',
                created   TEXT NOT NULL,
                updated   TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_key ON memories(key);

            CREATE TABLE IF NOT EXISTS summaries (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id    TEXT NOT NULL,
                summary   TEXT NOT NULL,
                created   TEXT NOT NULL
            );
        """)


def memory_store(key: str, value: str, tags: str = "") -> str:
    """Upsert a memory entry. Returns confirmation string."""
    now = datetime.utcnow().isoformat()
    try:
        with _connect() as conn:
            conn.execute("""
                INSERT INTO memories (key, value, tags, created, updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value   = excluded.value,
                    tags    = excluded.tags,
                    updated = excluded.updated
            """, (key, value, tags, now, now))
        return f"OK: Memory stored → key='{key}'"
    except Exception as e:
        return f"ERROR storing memory: {e}"


def memory_search(query: str, limit: int = 5) -> str:
    """
    Search memories by key or value substring match.
    Returns formatted results string.
    """
    try:
        with _connect() as conn:
            rows = conn.execute("""
                SELECT key, value, tags, updated
                FROM memories
                WHERE key LIKE ? OR value LIKE ? OR tags LIKE ?
                ORDER BY updated DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()

        if not rows:
            return f"No memories found matching '{query}'."

        lines = [f"Found {len(rows)} memory/memories matching '{query}':\n"]
        for row in rows:
            lines.append(f"  KEY:     {row['key']}")
            lines.append(f"  VALUE:   {row['value']}")
            lines.append(f"  TAGS:    {row['tags']}")
            lines.append(f"  UPDATED: {row['updated']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR searching memory: {e}"


def store_summary(run_id: str, summary: str) -> None:
    """Store a conversation summary (used by context manager)."""
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO summaries (run_id, summary, created) VALUES (?, ?, ?)",
            (run_id, summary, now)
        )


def get_summaries(run_id: str) -> list[str]:
    """Retrieve all summaries for a run."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT summary FROM summaries WHERE run_id=? ORDER BY id",
            (run_id,)
        ).fetchall()
    return [r["summary"] for r in rows]


# Initialize on import
init_db()