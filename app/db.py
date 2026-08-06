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

-- What the user actually does: what they capture, what they ask, what they
-- act on. This is the raw material for reflection (app/reflect.py) -- the
-- assistant can only improve at serving someone it has observed.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    entry_id INTEGER REFERENCES entries(id) ON DELETE SET NULL,
    data TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS events_kind_idx ON events(kind);
CREATE INDEX IF NOT EXISTS events_created_idx ON events(created_at);

-- Several files can belong to one entry: a project is often three
-- screenshots plus a paragraph of notes, and splitting those into separate
-- entries loses the fact that they describe the same thing. entries.file_path
-- still points at the first attachment so older callers keep working.
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    extracted_text TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS attachments_entry_idx ON attachments(entry_id);

-- Every change to a record, with the values it replaced. Saying "Notion went
-- up to $12" updates the existing subscription rather than creating a second
-- one -- but a wrong match must be recoverable, so nothing is overwritten
-- without the previous value being written down first.
CREATE TABLE IF NOT EXISTS facet_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facet_id INTEGER NOT NULL REFERENCES facets(id) ON DELETE CASCADE,
    entry_id INTEGER REFERENCES entries(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    changes TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS facet_revisions_facet_idx ON facet_revisions(facet_id);

-- Every model call, with what it cost. Organizing one capture can be several
-- calls across several skills, so "how much am I spending on this thing" is
-- not answerable from the entry count -- it needs the calls themselves.
-- cost_usd is NULL, not 0, when the model has no known rate (app/pricing.py).
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'other',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS llm_calls_created_idx ON llm_calls(created_at);
CREATE INDEX IF NOT EXISTS llm_calls_operation_idx ON llm_calls(operation);
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
        cur.execute("SELECT * FROM attachments WHERE entry_id = ? ORDER BY id", (entry_id,))
        entry["attachments"] = [dict(r) for r in cur.fetchall()]
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


def insert_attachment(
    *,
    entry_id: int,
    source_type: str,
    file_path: str,
    original_filename: str = "",
    extracted_text: str = "",
) -> int:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO attachments
                (entry_id, created_at, source_type, file_path, original_filename, extracted_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry_id, now_iso(), source_type, file_path, original_filename, extracted_text),
        )
        return cur.lastrowid


def list_attachments(entry_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM attachments WHERE entry_id = ? ORDER BY id", (entry_id,))
        return [dict(r) for r in cur.fetchall()]


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


def update_facet(facet_id: int, **fields) -> bool:
    """Update a facet's content and its promoted columns.

    Used when the user answers a follow-up question -- the facet is rebuilt
    through the normal path so promotions stay normalized.
    """
    allowed = {
        "label", "data", "due_at", "cadence", "amount",
        "currency", "identity", "vendor", "status",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Cannot update facet columns: {', '.join(sorted(unknown))}")
    if not fields:
        return False
    if "data" in fields:
        fields["data"] = json.dumps(fields["data"] or {})

    assignments = ", ".join(f"{k} = ?" for k in fields)
    with db_cursor() as cur:
        cur.execute(f"UPDATE facets SET {assignments} WHERE id = ?", (*fields.values(), facet_id))
        return cur.rowcount > 0


def insert_facet_revision(*, facet_id: int, entry_id: int | None, changes: dict) -> int:
    """Record what a change replaced, so a wrong match can be undone."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO facet_revisions (facet_id, entry_id, created_at, changes) VALUES (?, ?, ?, ?)",
            (facet_id, entry_id, now_iso(), json.dumps(changes or {})),
        )
        return cur.lastrowid


def list_facet_revisions(facet_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM facet_revisions WHERE facet_id = ? ORDER BY id DESC", (facet_id,)
        )
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            d["changes"] = json.loads(d.get("changes") or "{}")
            rows.append(d)
        return rows


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
        try:
            cur.execute("SELECT key, value FROM settings")
        except sqlite3.OperationalError:
            # Table not created yet (settings read before init_db). Defaults
            # in app/settings.py are the right answer in that state.
            return {}
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


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------


def log_event(*, kind: str, entry_id: int | None = None, data: dict | None = None) -> None:
    """Record something the user did.

    Never raises: an analytics write must not be able to fail a capture.
    """
    try:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO events (created_at, kind, entry_id, data) VALUES (?, ?, ?, ?)",
                (now_iso(), kind, entry_id, json.dumps(data or {})),
            )
    except sqlite3.Error:
        pass


def list_events(*, kind: str | None = None, limit: int = 100) -> list[dict]:
    with db_cursor() as cur:
        if kind:
            cur.execute(
                "SELECT * FROM events WHERE kind = ? ORDER BY id DESC LIMIT ?", (kind, limit)
            )
        else:
            cur.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            d["data"] = json.loads(d.get("data") or "{}")
            rows.append(d)
        return rows


def count_events_by_kind() -> dict[str, int]:
    with db_cursor() as cur:
        cur.execute("SELECT kind, COUNT(*) AS c FROM events GROUP BY kind")
        return {r["kind"]: r["c"] for r in cur.fetchall()}


def list_entries_without_facets(limit: int = 40) -> list[dict]:
    """Entries whose skill fired but extracted nothing structured.

    A weaker signal than falling through to `general`, but it catches the
    case that one misses: a skill that *plausibly* matched and then had
    nothing useful to record -- e.g. workout logs filed as journal entries.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT entries.* FROM entries
            LEFT JOIN facets ON facets.entry_id = entries.id
            WHERE facets.id IS NULL AND entries.skill != 'general'
            ORDER BY entries.id DESC LIMIT ?
            """,
            (limit,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]


def list_entries_by_skill(skill: str, limit: int = 40) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM entries WHERE skill = ? ORDER BY id DESC LIMIT ?", (skill, limit)
        )
        return [row_to_dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Model usage
# ---------------------------------------------------------------------------


def log_llm_call(
    *,
    provider: str,
    model: str,
    operation: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float | None = None,
    duration_ms: int = 0,
    ok: bool = True,
    error: str = "",
) -> None:
    """Record one model call.

    Never raises, for the same reason `log_event` doesn't: accounting must not
    be able to fail the work it is accounting for.
    """
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_calls (
                    created_at, provider, model, operation, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, cost_usd, duration_ms, ok, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    provider,
                    model,
                    operation,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    cost_usd,
                    duration_ms,
                    1 if ok else 0,
                    error[:500],
                ),
            )
    except sqlite3.Error:
        pass


_USAGE_COLUMNS = """
    COUNT(*) AS calls,
    COALESCE(SUM(input_tokens), 0) AS input_tokens,
    COALESCE(SUM(output_tokens), 0) AS output_tokens,
    COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
    COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(SUM(cost_usd), 0) AS cost_usd,
    COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failed,
    COALESCE(SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END), 0) AS unpriced
"""


def usage_summary(*, since: str | None = None) -> dict:
    """Totals across every call, optionally from `since` (ISO) onwards."""
    with db_cursor() as cur:
        if since:
            cur.execute(f"SELECT {_USAGE_COLUMNS} FROM llm_calls WHERE created_at >= ?", (since,))
        else:
            cur.execute(f"SELECT {_USAGE_COLUMNS} FROM llm_calls")
        return dict(cur.fetchone())


def usage_by(field: str, *, since: str | None = None, limit: int = 20) -> list[dict]:
    """Totals grouped by one column -- `model`, `operation`, or `provider`.

    `field` is checked against a fixed set rather than interpolated blindly:
    it reaches SQL as a column name, where a bound parameter can't go.
    """
    if field not in ("model", "operation", "provider"):
        raise ValueError(f"cannot group usage by {field!r}")

    with db_cursor() as cur:
        where = "WHERE created_at >= ?" if since else ""
        params: tuple = (since, limit) if since else (limit,)
        cur.execute(
            f"""
            SELECT {field} AS name, {_USAGE_COLUMNS}
            FROM llm_calls {where}
            GROUP BY {field}
            ORDER BY cost_usd DESC, calls DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in cur.fetchall()]


def usage_daily(*, days: int = 30) -> list[dict]:
    """One row per day, oldest first, for the spend-over-time chart.

    Days with no calls are absent -- the frontend fills the gaps, since it
    already knows the window it asked for.
    """
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT substr(created_at, 1, 10) AS day, {_USAGE_COLUMNS}
            FROM llm_calls
            WHERE created_at >= date('now', ?)
            GROUP BY day
            ORDER BY day ASC
            """,
            (f"-{max(int(days), 1)} days",),
        )
        return [dict(row) for row in cur.fetchall()]


def list_llm_calls(*, limit: int = 50) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


def reconcile_running_jobs() -> int:
    """Fail jobs left `running` by a process that died mid-flight.

    Jobs execute on a thread inside this process, so at startup nothing can
    legitimately still be running: any such row is a job whose process was
    killed -- most often by the dev server reloading when a code job edited
    the source it was watching. Left alone they'd sit at `running` forever.
    """
    message = (
        "Interrupted: the server restarted while this job was running. If it was a code "
        "change, check `git branch` and `git status` -- the working tree may have been "
        "left on its selfmod branch."
    )
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE mod_jobs
            SET status = 'failed', error = ?, finished_at = ?, updated_at = ?
            WHERE status = 'running'
            """,
            (message, now_iso(), now_iso()),
        )
        return cur.rowcount


def count_jobs_by_status() -> dict[str, int]:
    with db_cursor() as cur:
        cur.execute("SELECT status, COUNT(*) AS c FROM mod_jobs GROUP BY status")
        return {r["status"]: r["c"] for r in cur.fetchall()}
