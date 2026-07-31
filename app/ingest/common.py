from app import db
from app.organize import organize


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

    return db.get_entry(entry_id)
