"""Retrieval-augmented question answering over the local knowledge base.

Retrieval is plain SQLite FTS5 keyword search (no embeddings / vector DB
needed at personal-journal scale) -- Claude does the semantic heavy lifting
once it has the candidate entries in context.
"""

import re

from app import db, llm
from app.config import SEARCH_CANDIDATE_LIMIT, SEARCH_SNIPPET_LIMIT
from app.prompts import load_prompt

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "of", "in", "on",
    "at", "to", "for", "and", "or", "what", "when", "where", "who", "how", "why",
    "i", "me", "my", "about", "with", "that", "this", "it", "have", "has", "had", "be",
    "you", "your", "did", "tell", "know",
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": (
                "A direct, well-written answer to the user's question, based only on the "
                "provided entries. If the entries don't contain enough information, say so "
                "plainly rather than guessing."
            ),
        },
        "source_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Ids of the entries actually used to answer the question. Empty if none were relevant.",
        },
    },
    "required": ["answer", "source_ids"],
    "additionalProperties": False,
}

def _build_fts_query(question: str) -> str:
    tokens = [t.lower() for t in _TOKEN_RE.findall(question)]
    filtered = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if not filtered:
        filtered = tokens
    if not filtered:
        return ""
    return " OR ".join(f'"{t}"' for t in filtered)


def _search_candidates(question: str, limit: int = SEARCH_CANDIDATE_LIMIT) -> list[dict]:
    fts_query = _build_fts_query(question)
    results: list[dict] = []
    seen_ids: set[int] = set()

    if fts_query:
        with db.db_cursor() as cur:
            cur.execute(
                """
                SELECT entries.*, bm25(entries_fts) as rank
                FROM entries_fts
                JOIN entries ON entries.id = entries_fts.rowid
                WHERE entries_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            )
            for row in cur.fetchall():
                d = db.row_to_dict(row)
                if d["id"] not in seen_ids:
                    seen_ids.add(d["id"])
                    results.append(d)

    # Top up with the most recent entries so the model has something to
    # reason over even when keyword search comes up short.
    if len(results) < limit:
        for d in db.list_entries(limit=limit - len(results)):
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                results.append(d)

    return results[:limit]


def _format_context(entries: list[dict]) -> str:
    blocks = []
    for e in entries:
        snippet = e["raw_text"][:SEARCH_SNIPPET_LIMIT]
        tags = ", ".join(e.get("tags") or [])
        blocks.append(
            f"[Entry {e['id']}] ({e['source_type']}, category: {e['category']}, saved {e['created_at']})\n"
            f"Title: {e['title']}\n"
            f"Tags: {tags}\n"
            f"Summary: {e['summary']}\n"
            f"Content: {snippet}"
        )
    return "\n\n---\n\n".join(blocks)


def ask(question: str) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("Question is empty")

    candidates = _search_candidates(question)
    context = _format_context(candidates) if candidates else "(No entries saved yet.)"

    data = llm.complete_json(
        system=load_prompt("ask_system"),
        user_content=f"Knowledge base entries:\n\n{context}\n\n---\n\nQuestion: {question}",
        schema=ANSWER_SCHEMA,
        max_tokens=2048,
        effort="medium",
        schema_name="answer",
    )
    if data is None:
        return {"answer": "I can't help with that request.", "sources": []}

    by_id = {e["id"]: e for e in candidates}
    sources = [by_id[i] for i in data.get("source_ids", []) if i in by_id]

    return {"answer": data.get("answer", ""), "sources": sources}
