"""Deciding whether a captured record updates an existing one.

"I subscribed to Notion, $10/month" and, two months later, "Notion went up to
$12" describe *one* subscription. Without this the second note creates a
second record and the dashboard slowly fills with duplicates.

Which fields make two records the same is declared per skill
(`identity_fields`), never in Python. A skill that declares none is never
matched -- each receipt, journal entry and meeting note is its own thing, and
merging those would be wrong.

Matching is deliberately conservative:

- Candidates are shortlisted cheaply on the identity fields, so most captures
  never reach the model at all.
- A match is only applied when the model is confident. A duplicate is easy to
  spot and delete; a wrong merge quietly corrupts a record you trust.
- Nothing is overwritten without the previous value being written to
  facet_revisions first, so any merge can be undone.
"""

from __future__ import annotations

import re

from app import db, llm, skills
from app.facets import PROMOTABLE_COLUMNS, build_facet
from app.prompts import load_prompt

# How many existing records of the same kind to consider at all.
CANDIDATE_POOL = 60
# How many to actually show the model.
MAX_CANDIDATES = 8

EMPTY = (None, "", [], {})

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "match_id": {
            "type": ["integer", "null"],
            "description": "The id of the existing record this new information updates, or null if it's a different thing.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How certain you are. Use 'high' only when the records are unmistakably the same thing.",
        },
        "reason": {
            "type": "string",
            "description": "One short sentence naming what made them the same or different.",
        },
    },
    "required": ["match_id", "confidence", "reason"],
    "additionalProperties": False,
}


def _normalize(value) -> str:
    """Loose key for comparing names: 'Notion Plus' ~ 'notion  plus'."""
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return text


def _identity_values(skill, data: dict) -> list[str]:
    values = []
    for field_name in skill.identity_fields:
        normalized = _normalize(data.get(field_name))
        if normalized:
            values.append(normalized)
    return values


def shortlist(skill, facet: dict) -> list[dict]:
    """Existing records of this kind that plausibly describe the same thing.

    Cheap and generous -- this only decides what's worth showing the model.
    """
    wanted = _identity_values(skill, facet.get("data") or {})
    if not wanted:
        return []

    scored = []
    for existing in db.list_facets(kind=skill.id, limit=CANDIDATE_POOL):
        have = _identity_values(skill, existing.get("data") or {})
        if not have:
            continue
        score = 0
        for a in wanted:
            for b in have:
                if a == b:
                    score += 2
                elif a in b or b in a:
                    score += 1
        if score:
            scored.append((score, existing))

    scored.sort(key=lambda pair: (-pair[0], -pair[1]["id"]))
    return [existing for _, existing in scored[:MAX_CANDIDATES]]


def _describe(facet: dict) -> str:
    data = {k: v for k, v in (facet.get("data") or {}).items() if v not in EMPTY}
    parts = [f"id {facet['id']}", facet.get("label") or ""]
    if facet.get("status") and facet["status"] != "open":
        parts.append(f"status: {facet['status']}")
    return f"- {' | '.join(p for p in parts if p)}\n  {data}"


def find_match(skill, facet: dict) -> dict | None:
    """The existing record this facet updates, or None to create a new one."""
    candidates = shortlist(skill, facet)
    if not candidates:
        return None

    new_data = {k: v for k, v in (facet.get("data") or {}).items() if v not in EMPTY}
    listing = "\n".join(_describe(c) for c in candidates)

    try:
        result = llm.complete_json(
            system=load_prompt("record_match"),
            user_content=(
                f"Record type: {skill.id}\n"
                f"Identified by: {', '.join(skill.identity_fields)}\n\n"
                f"Existing records:\n{listing}\n\n"
                f"Newly captured:\n- {facet.get('label') or ''}\n  {new_data}"
            ),
            schema=MATCH_SCHEMA,
            max_tokens=400,
            effort="low",
            schema_name="record_match",
            operation="match_record",
        )
    except llm.LLMError:
        # If matching is unavailable, create a new record. A duplicate is
        # visible and deletable; a bad merge is neither.
        return None

    if not result or result.get("confidence") != "high":
        return None

    match_id = result.get("match_id")
    return next((c for c in candidates if c["id"] == match_id), None)


def apply_update(*, existing: dict, skill, incoming: dict, entry_id: int) -> dict:
    """Fold new information into an existing record, keeping what it replaced.

    Empty incoming values never clear a field: "I cancelled Notion" shouldn't
    wipe the price just because that note didn't mention it.
    """
    old_data = existing.get("data") or {}
    new_data = {k: v for k, v in (incoming.get("data") or {}).items() if v not in EMPTY}

    changed = {k: {"from": old_data.get(k), "to": v} for k, v in new_data.items() if old_data.get(k) != v}

    merged = {**old_data, **new_data}
    rebuilt = build_facet(skill, {**merged, "label": incoming.get("label") or existing.get("label") or ""})
    if rebuilt is None:
        return existing

    # `status` is only present when the skill promotes it and the value was
    # recognized; absent means "leave it as it is", not "clear it".
    columns = {c: rebuilt[c] for c in PROMOTABLE_COLUMNS if c in rebuilt}
    for column, value in columns.items():
        if existing.get(column) != value:
            changed[column] = {"from": existing.get(column), "to": value}

    if not changed:
        # Nothing new -- still worth noting the record was mentioned again.
        db.insert_facet_revision(facet_id=existing["id"], entry_id=entry_id, changes={})
        return db.get_facet(existing["id"])

    db.insert_facet_revision(facet_id=existing["id"], entry_id=entry_id, changes=changed)
    db.update_facet(
        existing["id"],
        label=rebuilt.get("label") or existing.get("label") or "",
        data=rebuilt["data"],
        **columns,
    )
    updated = db.get_facet(existing["id"])
    updated["changed_fields"] = sorted(changed)
    return updated
