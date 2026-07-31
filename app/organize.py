"""Turns raw ingested text into structured metadata.

Two Claude calls, both schema/prompt-driven from disk (nothing hardcoded):

1. Skill selection -- a cheap, low-effort call shown only {id, description}
   for every skill (skills.skills_menu). Progressive disclosure: the full
   instructions and extra schema for a skill are never sent unless it's
   picked.
2. Extraction -- once a skill is picked, its full instructions and
   extra_schema are merged into the request so the model can fill
   skill-specific fields (e.g. a recipe's ingredients/steps) alongside the
   universal title/summary/category/tags.
"""

import json

from app.claude_client import first_text, get_client
from app.config import MODEL, ORGANIZE_TEXT_LIMIT
from app.prompts import load_prompt
from app.skills import GENERAL_SKILL_ID, get_skill, skills_menu

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


def _skill_select_schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"skill_id": {"type": "string", "enum": ids}},
        "required": ["skill_id"],
        "additionalProperties": False,
    }


def _select_skill(raw_text: str, source_type: str) -> str:
    menu = skills_menu(source_type)
    if not menu:
        return GENERAL_SKILL_ID
    ids = [s["id"] for s in menu]
    if len(ids) == 1:
        return ids[0]

    menu_text = "\n".join(f"- {s['id']}: {s['description']}" for s in menu)
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=load_prompt("skill_selector"),
        output_config={
            "format": {"type": "json_schema", "schema": _skill_select_schema(ids)},
            "effort": "low",
        },
        messages=[
            {
                "role": "user",
                "content": f"Skills:\n{menu_text}\n\nContent (may be truncated):\n\"\"\"\n{raw_text[:2000]}\n\"\"\"",
            }
        ],
    )

    if response.stop_reason == "refusal":
        return GENERAL_SKILL_ID
    try:
        data = json.loads(first_text(response.content))
        picked = data.get("skill_id")
        return picked if picked in ids else GENERAL_SKILL_ID
    except (json.JSONDecodeError, TypeError):
        return GENERAL_SKILL_ID


def _build_schema(extra_schema: dict) -> dict:
    properties = {**BASE_PROPERTIES, **extra_schema}
    required = BASE_REQUIRED + [k for k in extra_schema if k not in BASE_REQUIRED]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _fallback(raw_text: str, skill_id: str) -> dict:
    return {
        "title": (raw_text[:60] or "Untitled entry").strip(),
        "summary": "",
        "category": "Other",
        "tags": [],
        "skill": skill_id,
        "extra": {},
    }


def organize(
    raw_text: str,
    *,
    source_type: str = "text",
    source_hint: str = "",
    existing_categories: list[str] | None = None,
) -> dict:
    """Select a skill, then extract structured metadata using it.

    Returns a dict with title/summary/category/tags plus `skill` (the id of
    the skill that was used) and `extra` (any skill-specific fields).
    """
    truncated = raw_text[:ORGANIZE_TEXT_LIMIT]
    skill_id = _select_skill(truncated, source_type)
    skill = get_skill(skill_id) or get_skill(GENERAL_SKILL_ID)
    if skill is None:
        return _fallback(raw_text, skill_id)

    schema = _build_schema(skill.extra_schema)
    system_prompt = load_prompt("organize_base")
    if skill.instructions:
        system_prompt = f"{system_prompt}\n\n---\nSelected skill: {skill.id}\n{skill.instructions}"

    category_hint = ""
    if existing_categories:
        category_hint = (
            "\n\nExisting categories already in use (prefer reusing one of these if it fits): "
            + ", ".join(existing_categories)
        )

    user_content = (
        f"{source_hint}\n\nContent to organize:\n\"\"\"\n{truncated}\n\"\"\"{category_hint}"
    ).strip()

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1536,
        system=system_prompt,
        output_config={
            "format": {"type": "json_schema", "schema": schema},
            "effort": "low",
        },
        messages=[{"role": "user", "content": user_content}],
    )

    if response.stop_reason == "refusal":
        return _fallback(raw_text, skill_id)

    text = first_text(response.content)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _fallback(raw_text, skill_id)

    data.setdefault("title", "Untitled entry")
    data.setdefault("summary", "")
    data.setdefault("category", "Other")
    data.setdefault("tags", [])

    extra = {k: data.pop(k) for k in list(skill.extra_schema) if k in data}
    data["skill"] = skill_id
    data["extra"] = extra
    return data
