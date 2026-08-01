"""Asking follow-up questions instead of silently recording a blank.

When a capture leaves a field empty that the skill says matters -- what a
subscription costs, how often it bills, what a project is built with -- the
right move is to ask rather than store a null nobody notices.

Which fields are worth asking about is declared in each skill's markdown
(`ask_if_missing`), never in Python. No code here knows that a subscription
has a "cost"; it only knows how to find fields a skill flagged and how to
feed answers back through that skill's own schema.
"""

from __future__ import annotations

from app import db, llm, skills
from app.facets import build_facet
from app.prompts import load_prompt, today_context

# Nothing meaningful was extracted for a field if it came back as any of
# these -- the same emptiness test used when building facets.
EMPTY = (None, "", [], {})


def questions_for_facet(facet: dict) -> list[dict]:
    """Fields this facet's skill wants filled in but that came back empty."""
    skill = skills.get_skill(facet["kind"])
    if skill is None or not skill.ask_if_missing:
        return []

    data = facet.get("data") or {}
    questions = []
    for field_name in skill.ask_if_missing:
        # Only ask about fields the skill actually declares -- a stale
        # ask_if_missing entry shouldn't produce an unanswerable question.
        if field_name not in skill.extra_schema:
            continue
        if data.get(field_name) not in EMPTY:
            continue
        questions.append(
            {
                "facet_id": facet["id"],
                "kind": facet["kind"],
                "field": field_name,
                "question": skill.question_for(field_name),
            }
        )
    return questions


def pending_questions(entry: dict) -> list[dict]:
    """Every unanswered question across an entry's facets."""
    questions: list[dict] = []
    for facet in entry.get("facets") or []:
        questions.extend(questions_for_facet(facet))
    return questions


def with_questions(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    entry["pending_questions"] = pending_questions(entry)
    return entry


def _answer_schema(skill, fields: list[str]) -> dict:
    """A schema covering just the fields being answered.

    Built from the skill's own extra_schema, so the answer is parsed under
    exactly the same rules as the original extraction.
    """
    properties = {name: skill.extra_schema[name] for name in fields}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def apply_answers(*, facet_id: int, answers: dict[str, str]) -> dict:
    """Fold the user's replies back into a facet.

    The replies are free text ("ten dollars a month", "next Tuesday"), so they
    go through the model using the skill's own field definitions rather than
    being written in raw -- that's what keeps a promoted column like `due_at`
    or `amount` in the shape queries expect.
    """
    facet = db.get_facet(facet_id)
    if facet is None:
        raise ValueError(f"Facet {facet_id} not found")

    skill = skills.get_skill(facet["kind"])
    if skill is None:
        raise ValueError(f"No skill named '{facet['kind']}' is installed any more")

    wanted = {
        name: str(value).strip()
        for name, value in (answers or {}).items()
        if name in skill.extra_schema and str(value or "").strip()
    }
    if not wanted:
        raise ValueError("No answers were provided")

    entry = db.get_entry(facet["entry_id"])
    original = (entry or {}).get("raw_text", "")[:4000]
    data = facet.get("data") or {}
    known = {k: v for k, v in data.items() if v not in EMPTY}

    # A reply often carries more than the field it was asked about -- "eight
    # dollars a month" answers the cost *and* names the currency. So offer
    # every still-empty field, not just the ones asked, and let the model fill
    # whatever the user actually said. Fields already filled are never
    # included, so an answer can't quietly overwrite something.
    fillable = [
        name for name in skill.extra_schema if name in wanted or data.get(name) in EMPTY
    ]

    replies = "\n".join(f"- {skill.question_for(name)}\n  Answer: {value}" for name, value in wanted.items())
    user_content = (
        f"{today_context()}\n\n"
        f'Original note:\n"""\n{original}\n"""\n\n'
        f"Already recorded: {known or '(nothing)'}\n\n"
        f"The user was asked, and replied:\n{replies}"
    )

    parsed = llm.complete_json(
        system=load_prompt("clarify"),
        user_content=user_content,
        schema=_answer_schema(skill, fillable),
        max_tokens=1024,
        effort="low",
        schema_name="clarification",
    )
    if parsed is None:
        raise ValueError("The model could not interpret those answers")

    # Rebuild the facet through the normal path so promoted columns are
    # recomputed and normalized exactly as they are on first capture.
    accepted = {k: v for k, v in parsed.items() if k in fillable and v not in EMPTY}

    if not accepted:
        # "I don't know" is a legitimate reply, not an error. Record nothing
        # so the field stays empty and gets asked again, and tell the caller
        # so it can say the answer didn't land.
        facet["recorded_fields"] = []
        return facet

    merged = {**data, **accepted}
    rebuilt = build_facet(skill, {**merged, "label": facet.get("label") or ""})
    if rebuilt is None:
        raise ValueError("Those answers left the record empty")

    db.update_facet(
        facet_id,
        label=rebuilt.get("label") or facet.get("label") or "",
        data=rebuilt["data"],
        due_at=rebuilt.get("due_at"),
        cadence=rebuilt.get("cadence"),
        amount=rebuilt.get("amount"),
        currency=rebuilt.get("currency"),
        identity=rebuilt.get("identity"),
        vendor=rebuilt.get("vendor"),
    )
    db.log_event(
        kind="clarification",
        entry_id=facet["entry_id"],
        data={"facet_id": facet_id, "kind": facet["kind"], "fields": sorted(accepted)},
    )
    updated = db.get_facet(facet_id)
    updated["recorded_fields"] = sorted(accepted)
    return updated
