from app import db, selfmod
from app.organize import organize

# The skill whose facets describe a change to the app itself.
FEATURE_REQUEST_KIND = "feature-request"


def _queue_modification(entry_id: int, facet: dict) -> None:
    """Turn a feature-request facet into a modification job.

    Always creates the job; app/settings.py decides whether it runs now or
    waits for the user. A failure here must never lose the captured entry,
    which is the thing the user actually asked to save.
    """
    data = facet.get("data") or {}
    prompt = (data.get("change_prompt") or "").strip()
    if not prompt:
        return
    kind = data.get("change_kind") if data.get("change_kind") in ("skill", "code") else "code"
    try:
        selfmod.create_request(
            title=(data.get("change_title") or facet.get("label") or "").strip(),
            prompt=prompt,
            kind=kind,
            origin="capture",
            entry_id=entry_id,
        )
    except Exception:
        pass


def create_entry(
    *,
    source_type: str,
    raw_text: str,
    source_hint: str = "",
    source_url: str | None = None,
    file_path: str | None = None,
    original_filename: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Organize raw_text with Claude and persist the resulting entry."""
    existing_categories = [c["category"] for c in db.list_categories() if c["category"]]
    meta = organize(
        raw_text,
        source_type=source_type,
        source_hint=source_hint,
        existing_categories=existing_categories,
    )

    # `skills` records every skill that fired; `skill` stays the primary one
    # so existing callers and the library UI keep working unchanged.
    combined_metadata = {**(metadata or {}), "skills": meta.get("skills", [])}

    entry_id = db.insert_entry(
        source_type=source_type,
        title=meta["title"],
        raw_text=raw_text,
        summary=meta["summary"],
        category=meta["category"],
        tags=meta["tags"],
        skill=meta.get("skill", "general"),
        source_url=source_url,
        file_path=file_path,
        original_filename=original_filename,
        metadata=combined_metadata,
    )

    for facet in meta.get("facets", []):
        db.insert_facet(entry_id=entry_id, **facet)
        if facet.get("kind") == FEATURE_REQUEST_KIND:
            _queue_modification(entry_id, facet)

    return db.get_entry(entry_id)
