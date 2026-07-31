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

-- One capture can be several things at once: "subscribed to Notion with
-- x@gmail.com, $10/mo, renews the 5th, remind me" is an account AND a
-- subscription AND a reminder. Each of those is a facet row.
--
-- `data` holds the full skill-specific extraction; the columns beside it are
-- the handful of fields worth querying across every kind (what's due, what
-- costs money, which account). Skills opt into those columns via a
-- `promote:` mapping in their frontmatter -- see app/facets.py.
CREATE TABLE IF NOT EXISTS facets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    due_at TEXT,
    cadence TEXT,
    amount REAL,
    currency TEXT,
    identity TEXT,
    vendor TEXT,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS facets_entry_idx ON facets(entry_id);
CREATE INDEX IF NOT EXISTS facets_kind_idx ON facets(kind);
CREATE INDEX IF NOT EXISTS facets_due_idx ON facets(due_at);
CREATE INDEX IF NOT EXISTS facets_status_idx ON facets(status);

-- User-editable runtime settings. Defaults live in app/settings.py; a row
-- here only exists once a value has been changed from its default.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Requests to change the app itself. Every request becomes a row whether or
-- not self-modification is enabled: the setting decides only whether the job
-- runs now or waits for the user to run it by hand. Nothing is ever silently
-- dropped, and a job's prompt stays readable after the fact.
CREATE TABLE IF NOT EXISTS mod_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'code',
    status TEXT NOT NULL DEFAULT 'pending',
    origin TEXT NOT NULL DEFAULT 'manual',
    entry_id INTEGER REFERENCES entries(id) ON DELETE SET NULL,
    branch TEXT,
    result TEXT NOT NULL DEFAULT '',
    error TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS mod_jobs_status_idx ON mod_jobs(status);
"""

# Facet lifecycle. Anything time-bound stays `open` until you act on it --
# that's what keeps it on the agenda.
FACET_STATUSES = ("open", "done", "dismissed")

# `skill` writes a skills/*.md file (data only, no code runs).
# `code`  hands the prompt to a coding agent that edits the app itself.
JOB_KINDS = ("skill", "code")

# pending -> the user must run it; running -> in flight; the rest are final.
JOB_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")


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


def facet_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["data"] = json.loads(d.get("data") or "{}")
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
        if not row:
            return None
        entry = row_to_dict(row)
        cur.execute("SELECT * FROM facets WHERE entry_id = ? ORDER BY id", (entry_id,))
        entry["facets"] = [facet_to_dict(r) for r in cur.fetchall()]
        return entry


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
        entries = [row_to_dict(r) for r in cur.fetchall()]
        _attach_facets(cur, entries)
        return entries


def _attach_facets(cur, entries: list[dict]) -> None:
    """Bulk-load facets for a page of entries (one query, not one per entry)."""
    for entry in entries:
        entry["facets"] = []
    if not entries:
        return
    by_id = {e["id"]: e for e in entries}
    placeholders = ",".join("?" * len(by_id))
    cur.execute(
        f"SELECT * FROM facets WHERE entry_id IN ({placeholders}) ORDER BY id",
        tuple(by_id),
    )
    for row in cur.fetchall():
        facet = facet_to_dict(row)
        by_id[facet["entry_id"]]["facets"].append(facet)


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


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

# Facet rows carry enough of their entry to be rendered on their own (on the
# agenda you want to see the title and category without a second fetch).
_FACET_SELECT = """
SELECT facets.*,
       entries.title AS entry_title,
       entries.category AS entry_category,
       entries.source_type AS entry_source_type
FROM facets
JOIN entries ON entries.id = facets.entry_id
"""


def insert_facet(
    *,
    entry_id: int,
    kind: str,
    label: str = "",
    data: dict | None = None,
    due_at: str | None = None,
    cadence: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    identity: str | None = None,
    vendor: str | None = None,
    status: str = "open",
) -> int:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO facets
                (entry_id, created_at, kind, label, data, due_at, cadence,
                 amount, currency, identity, vendor, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                now_iso(),
                kind,
                label,
                json.dumps(data or {}),
                due_at,
                cadence,
                amount,
                currency,
                identity,
                vendor,
                status,
            ),
        )
        return cur.lastrowid


def get_facet(facet_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute(f"{_FACET_SELECT} WHERE facets.id = ?", (facet_id,))
        row = cur.fetchone()
        return facet_to_dict(row) if row else None


def list_facets(
    *,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    clauses, params = [], []
    if kind:
        clauses.append("facets.kind = ?")
        params.append(kind)
    if status:
        clauses.append("facets.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    with db_cursor() as cur:
        cur.execute(f"{_FACET_SELECT} {where} ORDER BY facets.id DESC LIMIT ? OFFSET ?", params)
        return [facet_to_dict(r) for r in cur.fetchall()]


def list_due_facets(*, start: str | None = None, end: str | None = None) -> list[dict]:
    """Open facets with a due date, optionally bounded to a [start, end] window.

    Dates are compared on their `YYYY-MM-DD` prefix so a date-only due_at
    ("2026-08-05") and a timestamped one ("2026-08-05T09:00") both land in the
    right day regardless of which form the model produced.
    """
    clauses = ["facets.due_at IS NOT NULL", "facets.due_at != ''", "facets.status = 'open'"]
    params: list = []
    if start:
        clauses.append("substr(facets.due_at, 1, 10) >= ?")
        params.append(start[:10])
    if end:
        clauses.append("substr(facets.due_at, 1, 10) <= ?")
        params.append(end[:10])

    with db_cursor() as cur:
        cur.execute(
            f"{_FACET_SELECT} WHERE {' AND '.join(clauses)} ORDER BY facets.due_at ASC",
            params,
        )
        return [facet_to_dict(r) for r in cur.fetchall()]


def set_facet_status(facet_id: int, status: str) -> bool:
    if status not in FACET_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Expected one of: {', '.join(FACET_STATUSES)}")
    with db_cursor() as cur:
        cur.execute("UPDATE facets SET status = ? WHERE id = ?", (status, facet_id))
        return cur.rowcount > 0


def list_facet_kinds() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT kind,
                   COUNT(*) AS count,
                   SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count
            FROM facets GROUP BY kind ORDER BY count DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Settings -- only overrides are stored; defaults live in app/settings.py
# ---------------------------------------------------------------------------


def get_setting_overrides() -> dict[str, str]:
    with db_cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in cur.fetchall()}


def set_setting_override(key: str, value: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now_iso()),
        )


# ---------------------------------------------------------------------------
# Modification jobs
# ---------------------------------------------------------------------------


def insert_job(
    *,
    title: str,
    prompt: str,
    kind: str = "code",
    status: str = "pending",
    origin: str = "manual",
    entry_id: int | None = None,
) -> int:
    if kind not in JOB_KINDS:
        raise ValueError(f"Invalid kind '{kind}'. Expected one of: {', '.join(JOB_KINDS)}")
    if status not in JOB_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Expected one of: {', '.join(JOB_STATUSES)}")
    stamp = now_iso()
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mod_jobs (created_at, updated_at, title, prompt, kind, status, origin, entry_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (stamp, stamp, title, prompt, kind, status, origin, entry_id),
        )
        return cur.lastrowid


def get_job(job_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM mod_jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_jobs(*, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    with db_cursor() as cur:
        if status:
            cur.execute(
                "SELECT * FROM mod_jobs WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cur.execute("SELECT * FROM mod_jobs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        return [dict(r) for r in cur.fetchall()]


def update_job(job_id: int, **fields) -> bool:
    """Update whitelisted job columns. Always refreshes updated_at."""
    allowed = {"status", "result", "error", "branch", "started_at", "finished_at", "title"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Cannot update job columns: {', '.join(sorted(unknown))}")
    if fields.get("status") and fields["status"] not in JOB_STATUSES:
        raise ValueError(f"Invalid status '{fields['status']}'")

    fields["updated_at"] = now_iso()
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with db_cursor() as cur:
        cur.execute(f"UPDATE mod_jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))
        return cur.rowcount > 0


def claim_job(job_id: int) -> bool:
    """Move a job pending -> running, refusing if it isn't pending.

    The UPDATE tests the status itself so two concurrent run requests can't
    both start the same job.
    """
    with db_cursor() as cur:
        cur.execute(
            "UPDATE mod_jobs SET status = 'running', started_at = ?, updated_at = ?, error = NULL "
            "WHERE id = ? AND status = 'pending'",
            (now_iso(), now_iso(), job_id),
        )
        return cur.rowcount > 0


def count_jobs_by_status() -> dict[str, int]:
    with db_cursor() as cur:
        cur.execute("SELECT status, COUNT(*) AS c FROM mod_jobs GROUP BY status")
        return {r["status"]: r["c"] for r in cur.fetchall()}
