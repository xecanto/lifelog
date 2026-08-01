"""Dynamic skill loading.

A "skill" is a markdown file under skills/ with YAML frontmatter -- a
specialized way of organizing one kind of saved content (a recipe, a task, a
meeting note, ...). Nothing about the available skills is hardcoded in
Python: the directory is rescanned on every call, so adding, editing, or
deleting a .md file changes what the app can do without touching code or
restarting the server.

Selection is a two-step, progressive-disclosure pattern (mirrors how Claude
Agent Skills work): only {id, description} for every skill is ever shown to
Claude to pick from (cheap, small context); the full instructions + extra
schema for the *selected* skill are loaded only after it's chosen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from app.config import SKILLS_DIR

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

GENERAL_SKILL_ID = "general"


@dataclass
class Skill:
    id: str
    description: str
    applies_to: list[str] = field(default_factory=list)
    extra_schema: dict = field(default_factory=dict)
    # Maps a queryable facet column -> the name of one of this skill's
    # extra_schema fields, e.g. {"due_at": "next_renewal", "amount": "cost"}.
    # This is how a skill opts its data into the agenda and cross-kind
    # queries without any Python knowing the skill exists.
    promote: dict[str, str] = field(default_factory=dict)
    # Fields worth asking the user about when extraction leaves them empty,
    # as {field_name: question}. Declared per skill so no Python ever knows
    # that a subscription has a "cost" -- add the key to the markdown and the
    # app starts asking.
    ask_if_missing: dict[str, str] = field(default_factory=dict)
    instructions: str = ""

    def question_for(self, field_name: str) -> str:
        """The question to ask for a field, falling back to its description."""
        declared = (self.ask_if_missing.get(field_name) or "").strip()
        if declared:
            return declared
        definition = self.extra_schema.get(field_name) or {}
        described = str(definition.get("description") or "").strip()
        return described or f"What is the {field_name.replace('_', ' ')}?"


def parse_skill_text(text: str, *, fallback_id: str = "") -> Skill | None:
    """Parse skill markdown. Returns None if it has no usable frontmatter.

    Used both to load skills/ from disk and to validate a skill file authored
    by the assistant before it's written (see app/selfmod.py) -- validating
    through the same code path that loads them is the point.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    frontmatter_raw, body = match.groups()
    try:
        meta = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    skill_id = meta.get("name") or fallback_id
    # Accept either a plain list of field names or a {field: question} map,
    # so a skill can opt in with one line and refine the wording later.
    raw_ask = meta.get("ask_if_missing") or {}
    if isinstance(raw_ask, list):
        ask_if_missing = {str(name): "" for name in raw_ask}
    elif isinstance(raw_ask, dict):
        ask_if_missing = {str(k): str(v or "") for k, v in raw_ask.items()}
    else:
        ask_if_missing = {}

    return Skill(
        id=skill_id,
        description=meta.get("description", ""),
        applies_to=meta.get("applies_to") or ["text", "link", "file", "image", "voice"],
        extra_schema=meta.get("extra_schema") or {},
        promote=meta.get("promote") or {},
        ask_if_missing=ask_if_missing,
        instructions=body.strip(),
    )


def _parse_skill_file(path) -> Skill | None:
    return parse_skill_text(path.read_text(encoding="utf-8"), fallback_id=path.stem)


def _load_all() -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for path in sorted(SKILLS_DIR.glob("*.md")):
        skill = _parse_skill_file(path)
        if skill:
            skills[skill.id] = skill
    return skills


def list_skills(source_type: str | None = None) -> list[Skill]:
    values = list(_load_all().values())
    if source_type:
        values = [s for s in values if source_type in s.applies_to]
    return values


def get_skill(skill_id: str) -> Skill | None:
    return _load_all().get(skill_id)


def skills_menu(source_type: str | None = None) -> list[dict]:
    """Short {id, description} list -- what gets shown to Claude to pick from."""
    return [{"id": s.id, "description": s.description} for s in list_skills(source_type)]
