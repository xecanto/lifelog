import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    skill TEXT NOT NULL DEFAULT 'general',
    source_url TEXT,
    file_path TEXT,
    original_filename TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, raw_text, summary, tags, category,
    content='entries', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, title, raw_text, summary, tags, category)
  VALUES (new.id, new.title, new.raw_text, new.summary, new.tags, new.category);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, title, raw_text, summary, tags, category)
  VALUES('delete', old.id, old.title, old.raw_text, old.summary, old.tags, old.category);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, title, raw_text, summary, tags, category)
  VALUES('delete', old.id, old.title, old.raw_text, old.summary, old.tags, old.category);
  INSERT INTO entries_fts(rowid, title, raw_text, summary, tags, category)
  VALUES (new.id, new.title, new.raw_text, new.summary, new.tags, new.category);
END;
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the initial schema, for existing DBs."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    if "skill" not in existing:
        conn.execute("ALTER TABLE entries ADD COLUMN skill TEXT NOT NULL DEFAULT 'general'")


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["metadata"] = json.loads(d.get("metadata") or "{}")
    return d


def insert_entry(
    *,
    source_type: str,
    title: str,
    raw_text: str,
    summary: str,
    category: str,
    tags: list[str],
    skill: str = "general",
    source_url: str | None = None,
    file_path: str | None = None,
    original_filename: str | None = None,
    metadata: dict | None = None,
) -> int:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO entries
                (created_at, source_type, title, raw_text, summary, category,
                 tags, skill, source_url, file_path, original_filename, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                source_type,
                title,
                raw_text,
                summary,
                category,
                json.dumps(tags),
                skill,
                source_url,
                file_path,
                original_filename,
                json.dumps(metadata or {}),
            ),
        )
        return cur.lastrowid


def get_entry(entry_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cur.fetchone()
        return row_to_dict(row) if row else None


def list_entries(*, limit: int = 50, offset: int = 0, category: str | None = None) -> list[dict]:
    with db_cursor() as cur:
        if category:
            cur.execute(
                "SELECT * FROM entries WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (category, limit, offset),
            )
        else:
            cur.execute(
                "SELECT * FROM entries ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [row_to_dict(r) for r in cur.fetchall()]


def delete_entry(entry_id: int) -> bool:
    with db_cursor() as cur:
        cur.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cur.rowcount > 0


def list_categories() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT category, COUNT(*) as count FROM entries GROUP BY category ORDER BY count DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def count_entries() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as c FROM entries")
        return cur.fetchone()["c"]
