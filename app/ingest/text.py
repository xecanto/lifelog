from app.ingest.common import create_entry


def ingest_text(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Text is empty")
    return create_entry(
        source_type="text",
        raw_text=text,
        source_hint="This is a note typed or pasted directly by the user.",
    )
