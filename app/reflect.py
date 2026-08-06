"""Learning from use: notice what the app keeps failing to capture well.

The signal that matters most is content that fell through to the `general`
skill -- that's the app admitting it had no better idea what something was.
When the same shape shows up repeatedly there, a skill is missing. Questions
that returned no sources are the other half: things the user expected to have
saved and didn't.

Proposals become modification jobs like any other request, so the same
settings decide whether they run or wait (see app/selfmod.py). Reflection
never writes files itself.
"""

from __future__ import annotations

from collections import Counter

from app import db, llm, selfmod, skills
from app.prompts import load_prompt
from app.skills import GENERAL_SKILL_ID

# Below this there isn't enough usage for a pattern to mean anything, and
# proposals would just be noise the user has to read and dismiss.
MIN_ENTRIES_FOR_REFLECTION = 5
MAX_PROPOSALS = 3

REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What you noticed about how this knowledge base is being used. 1-4 short, specific points.",
        },
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short imperative title, max 10 words."},
                    "kind": {"type": "string", "enum": ["skill", "code"]},
                    "prompt": {
                        "type": "string",
                        "description": "A complete, standalone brief someone could act on without seeing these signals.",
                    },
                    "why": {
                        "type": "string",
                        "description": "The specific evidence in the signals that justifies this. Cite what you saw.",
                    },
                },
                "required": ["title", "kind", "prompt", "why"],
                "additionalProperties": False,
            },
            "description": f"Between 0 and {MAX_PROPOSALS} proposals. Empty is correct when nothing stands out.",
        },
    },
    "required": ["observations", "proposals"],
    "additionalProperties": False,
}


def gather_signals() -> dict:
    """Collect what usage says about the gaps, without calling a model."""
    total = db.count_entries()
    uncategorized = db.list_entries_by_skill(GENERAL_SKILL_ID, limit=40)

    tag_counts: Counter[str] = Counter()
    for entry in uncategorized:
        for tag in entry.get("tags") or []:
            cleaned = tag.strip().lower()
            if cleaned:
                tag_counts[cleaned] += 1

    unanswered = [
        event["data"].get("question", "")
        for event in db.list_events(kind="ask", limit=60)
        if not event["data"].get("source_count")
    ]

    unstructured = db.list_entries_without_facets(limit=25)

    # The signals above only detect the app *failing*. They can't see the
    # more common gap: a repeated shape that got scattered across several
    # loosely-fitting skills -- four job applications filed as task, event,
    # contact and journal look fine one at a time, and only read as a missing
    # skill when you see them together. So hand over recent entries with
    # their assigned skill and let the pattern be visible.
    recent = db.list_entries(limit=30)
    all_tags: Counter[str] = Counter()
    for entry in recent:
        for tag in entry.get("tags") or []:
            cleaned = tag.strip().lower()
            if cleaned:
                all_tags[cleaned] += 1

    return {
        "recent_entries": [
            {"title": e["title"], "skill": e["skill"], "tags": e["tags"]} for e in recent
        ],
        "common_tags": all_tags.most_common(20),
        "total_entries": total,
        "generic_entries": [
            {"title": e["title"], "summary": e["summary"], "tags": e["tags"]}
            for e in uncategorized[:20]
        ],
        "generic_count": len(uncategorized),
        "unstructured_entries": [
            {"title": e["title"], "skill": e["skill"], "summary": e["summary"], "tags": e["tags"]}
            for e in unstructured
        ],
        "recurring_tags": tag_counts.most_common(15),
        "unanswered_questions": [q for q in unanswered if q][:15],
        "facet_kinds": db.list_facet_kinds(),
        "existing_skills": [{"id": s.id, "description": s.description} for s in skills.list_skills()],
    }


def _format_signals(signals: dict) -> str:
    lines = [f"Total entries saved: {signals['total_entries']}"]

    if signals["recent_entries"]:
        lines.append(
            "\nRecent entries and the skill each was filed under. Look for a repeated "
            "subject scattered across DIFFERENT skills -- that's a missing skill, even "
            "though each entry looks correctly filed on its own:"
        )
        for entry in signals["recent_entries"]:
            tags = ", ".join(entry["tags"] or [])
            lines.append(f"- [{entry['skill']}] {entry['title']} [{tags}]")

    if signals["common_tags"]:
        lines.append("\nMost common tags overall:")
        lines.append(", ".join(f"{tag} ({count})" for tag, count in signals["common_tags"]))

    lines.append(
        f"\nEntries that fell through to the generic skill ({signals['generic_count']}) -- "
        "the app had no better idea what these were:"
    )
    for entry in signals["generic_entries"]:
        tags = ", ".join(entry["tags"] or [])
        lines.append(f"- {entry['title']} [{tags}] -- {entry['summary']}")
    if not signals["generic_entries"]:
        lines.append("- (none)")

    if signals["unstructured_entries"]:
        lines.append(
            "\nEntries where a skill matched but recorded no structured fields -- "
            "the skill may be a loose fit rather than the right one:"
        )
        for entry in signals["unstructured_entries"]:
            tags = ", ".join(entry["tags"] or [])
            lines.append(f"- [filed as {entry['skill']}] {entry['title']} [{tags}]")

    if signals["recurring_tags"]:
        lines.append("\nTags recurring among those:")
        lines.append(", ".join(f"{tag} ({count})" for tag, count in signals["recurring_tags"]))

    if signals["unanswered_questions"]:
        lines.append("\nQuestions the saved notes could not answer:")
        lines.extend(f"- {q}" for q in signals["unanswered_questions"])

    if signals["facet_kinds"]:
        lines.append("\nRecords actually being created:")
        lines.append(", ".join(f"{k['kind']} ({k['count']})" for k in signals["facet_kinds"]))

    lines.append("\nSkills that already exist -- do not propose anything these cover:")
    lines.extend(f"- {s['id']}: {s['description']}" for s in signals["existing_skills"])

    return "\n".join(lines)


def reflect(*, dry_run: bool = False) -> dict:
    """Look at usage and propose improvements.

    Proposals are filed as modification jobs; whether they run now or wait is
    the same settings decision as any other request. `dry_run` returns the
    proposals without filing anything.
    """
    signals = gather_signals()

    if signals["total_entries"] < MIN_ENTRIES_FOR_REFLECTION:
        return {
            "ran": False,
            "reason": (
                f"Only {signals['total_entries']} entries saved so far. "
                f"Reflection needs at least {MIN_ENTRIES_FOR_REFLECTION} to tell a pattern "
                "from a coincidence."
            ),
            "observations": [],
            "proposals": [],
            "jobs": [],
            "signals": signals,
        }

    data = llm.complete_json(
        system=load_prompt("reflect"),
        user_content=_format_signals(signals),
        schema=REFLECT_SCHEMA,
        max_tokens=2048,
        effort="high",
        schema_name="reflection",
        operation="reflect",
    )
    if data is None:
        return {
            "ran": False,
            "reason": "The model declined to review this activity.",
            "observations": [],
            "proposals": [],
            "jobs": [],
            "signals": signals,
        }

    existing_ids = {s["id"] for s in signals["existing_skills"]}
    proposals = []
    for proposal in (data.get("proposals") or [])[:MAX_PROPOSALS]:
        if not isinstance(proposal, dict) or not (proposal.get("prompt") or "").strip():
            continue
        # Cheap guard against re-proposing something already covered.
        if (proposal.get("title", "").strip().lower().replace(" ", "-")) in existing_ids:
            continue
        proposals.append(proposal)

    jobs = []
    if not dry_run:
        for proposal in proposals:
            try:
                jobs.append(
                    selfmod.create_request(
                        title=proposal["title"],
                        prompt=f"{proposal['prompt']}\n\n(Proposed by reflection: {proposal.get('why', '')})",
                        kind=proposal["kind"] if proposal.get("kind") in ("skill", "code") else "skill",
                        origin="reflection",
                    )
                )
            except ValueError:
                continue

        db.log_event(
            kind="reflection",
            data={"proposal_count": len(proposals), "observations": data.get("observations", [])},
        )

    return {
        "ran": True,
        "reason": "",
        "observations": data.get("observations", []),
        "proposals": proposals,
        "jobs": jobs,
        "signals": signals,
    }
