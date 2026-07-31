"""Turns raw ingested text into structured metadata.

Two Claude calls, both schema/prompt-driven from disk (nothing hardcoded):

1. Skill routing -- a cheap, low-effort call shown only {id, description}
   for every skill (skills.skills_menu). Progressive disclosure: the full
   instructions and extra schema for a skill are never sent unless it's
   picked. This returns a *set* of skills, not one: a single note can be an
   account, a subscription, and a reminder at the same time.
2. Extraction -- one call whose schema nests each selected skill's
   extra_schema under `facets.<skill_id>`, so every facet is filled in from
   the same reading of the content, with the fields kept separate. Each of
   those becomes a facet row (see app/facets.py).
"""

from datetime import datetime

from app import llm
from app.config import MAX_SKILLS_PER_ENTRY, ORGANIZE_TEXT_LIMIT
from app.facets import LABEL_FIELD, LABEL_SCHEMA, build_facet
from app.prompts import load_prompt
from app.skills import GENERAL_SKILL_ID, Skill, get_skill, skills_menu

BASE_PROPERTIES = {
    "title": {
        "type": "string",
        "description": "A short, specific, human-readable title for this entry (max 8 words). No quotes.",
    },
    "summary": {
        "type": "string",
        "description": "A 1-3 sentence summary capturing the key information someone would want to recall later.",
    },
    "category": {
        "type": "string",
        "description": (
            "A single broad category this entry belongs to, e.g. Work, Personal, Ideas, "
            "Health, Finance, Learning, Travel, Recipes, Relationships, Admin, Other. "
            "Reuse an existing category when it fits rather than inventing near-duplicates."
        ),
    },
    "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "3-6 short, lowercase, specific keyword tags for search (e.g. names, topics, places).",
    },
}
BASE_REQUIRED = ["title", "summary", "category", "tags"]


def _today_context() -> str:
    """Relative dates are useless to the model unless it knows what day it is.

    "remind me Friday" / "renews on the 5th" are the common case for
    reminders and subscriptions, so this is load-bearing for the agenda.
    """
    now = datetime.now().astimezone()
    return f"Today is {now.strftime('%A, %d %B %Y')} ({now.strftime('%Y-%m-%d')})."


# ---------------------------------------------------------------------------
# 1. Routing
# ---------------------------------------------------------------------------


def _skill_select_schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "skill_ids": {
                "type": "array",
                "items": {"type": "string", "enum": ids},
                "description": (
                    "Every skill that genuinely applies to this content, most central "
                    f"first. Usually 1-3, never more than {MAX_SKILLS_PER_ENTRY}."
                ),
            }
        },
        "required": ["skill_ids"],
        "additionalProperties": False,
    }


def _select_skills(raw_text: str, source_type: str) -> list[str]:
    menu = skills_menu(source_type)
    if not menu:
        return [GENERAL_SKILL_ID]
    ids = [s["id"] for s in menu]
    if len(ids) == 1:
        return ids

    menu_text = "\n".join(f"- {s['id']}: {s['description']}" for s in menu)
    try:
        data = llm.complete_json(
            system=load_prompt("skill_selector"),
            user_content=(
                f"{_today_context()}\n\nSkills:\n{menu_text}\n\n"
                f'Content (may be truncated):\n"""\n{raw_text[:2000]}\n"""'
            ),
            schema=_skill_select_schema(ids),
            max_tokens=300,
            effort="low",
            schema_name="skill_selection",
        )
    except llm.LLMError:
        # Routing is a convenience -- a provider hiccup shouldn't stop the
        # capture, it should just fall back to the general skill.
        return [GENERAL_SKILL_ID]

    if data is None:
        return [GENERAL_SKILL_ID]
    try:
        picked = [s for s in data.get("skill_ids", []) if s in ids]
    except (TypeError, AttributeError):
        return [GENERAL_SKILL_ID]

    deduped = list(dict.fromkeys(picked))[:MAX_SKILLS_PER_ENTRY]
    return deduped or [GENERAL_SKILL_ID]


# ---------------------------------------------------------------------------
# 2. Extraction
# ---------------------------------------------------------------------------


def _facet_schema(skill: Skill) -> dict:
    fields = {LABEL_FIELD: LABEL_SCHEMA, **skill.extra_schema}
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


def _build_schema(selected: list[Skill]) -> dict:
    properties = dict(BASE_PROPERTIES)
    required = list(BASE_REQUIRED)

    # Skills with no extra_schema (e.g. `general`) are pure categorization --
    # they're recorded on the entry itself and don't need a facet row.
    facet_props = {s.id: _facet_schema(s) for s in selected if s.extra_schema}
    if facet_props:
        properties["facets"] = {
            "type": "object",
            "properties": facet_props,
            "required": list(facet_props),
            "additionalProperties": False,
        }
        required.append("facets")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _build_system_prompt(selected: list[Skill]) -> str:
    parts = [load_prompt("organize_base")]
    for skill in selected:
        if skill.instructions:
            parts.append(f"---\nSkill `{skill.id}`:\n{skill.instructions}")
    return "\n\n".join(parts)


def _fallback(raw_text: str, skill_ids: list[str]) -> dict:
    return {
        "title": (raw_text[:60] or "Untitled entry").strip(),
        "summary": "",
        "category": "Other",
        "tags": [],
        "skill": skill_ids[0] if skill_ids else GENERAL_SKILL_ID,
        "skills": skill_ids or [GENERAL_SKILL_ID],
        "facets": [],
    }


def organize(
    raw_text: str,
    *,
    source_type: str = "text",
    source_hint: str = "",
    existing_categories: list[str] | None = None,
) -> dict:
    """Route to one or more skills, then extract all of them in one pass.

    Returns title/summary/category/tags plus `skill` (the primary skill id),
    `skills` (every skill that applied) and `facets` (ready-to-insert facet
    rows, already normalized).
    """
    truncated = raw_text[:ORGANIZE_TEXT_LIMIT]
    skill_ids = _select_skills(truncated, source_type)

    selected = [s for s in (get_skill(i) for i in skill_ids) if s is not None]
    if not selected:
        general = get_skill(GENERAL_SKILL_ID)
        if general is None:
            return _fallback(raw_text, skill_ids)
        selected = [general]

    category_hint = ""
    if existing_categories:
        category_hint = (
            "\n\nExisting categories already in use (prefer reusing one of these if it fits): "
            + ", ".join(existing_categories)
        )

    user_content = (
        f"{_today_context()}\n\n{source_hint}\n\n"
        f'Content to organize:\n"""\n{truncated}\n"""{category_hint}'
    ).strip()

    ids = [s.id for s in selected]
    data = llm.complete_json(
        system=_build_system_prompt(selected),
        user_content=user_content,
        schema=_build_schema(selected),
        max_tokens=4096,
        effort="medium",
        schema_name="entry_organization",
    )
    if data is None:
        return _fallback(raw_text, ids)

    data.setdefault("title", "Untitled entry")
    data.setdefault("summary", "")
    data.setdefault("category", "Other")
    data.setdefault("tags", [])

    raw_facets = data.pop("facets", None) or {}
    facets = []
    for skill in selected:
        extracted = raw_facets.get(skill.id)
        if not isinstance(extracted, dict):
            continue
        facet = build_facet(skill, extracted)
        if facet:
            facets.append(facet)

    data["skill"] = ids[0]
    data["skills"] = ids
    data["facets"] = facets
    return data
