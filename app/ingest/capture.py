"""One entry point that works out what you gave it.

Picking "text vs link vs file vs image vs voice" was busywork the user had to
do before every capture, and the answer is almost always obvious from the
input itself. This routes to the right ingester so the UI can be a single
box you drop anything into.

The per-type ingesters are unchanged and still usable directly; this only
decides which one to call.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ingest.common import create_entry
from app.ingest.files import TEXT_EXTENSIONS, store_and_extract
from app.ingest.images import store_and_describe
from app.ingest.links import ingest_link
from app.ingest.text import ingest_text
from app.ingest.voice import store_and_transcribe

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}

# A capture is a link only when the whole input is one URL. "check out
# https://x.com, looks useful" is a note that happens to contain a link --
# fetching the article would throw away what the user actually wrote.
_BARE_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_BARE_DOMAIN_RE = re.compile(
    r"^(?:www\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?$",
    re.IGNORECASE,
)


def detect_source(*, text: str | None = None, filename: str | None = None, content_type: str | None = None) -> str:
    """Work out which ingester an input belongs to.

    Separate from `capture` so the decision can be tested, and shown in the
    UI, without uploading anything.
    """
    if filename or content_type:
        ext = Path(filename or "").suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in AUDIO_EXTENSIONS:
            return "voice"
        if ext in DOCUMENT_EXTENSIONS:
            return "file"

        # Fall back to the browser-reported type when the name is unhelpful
        # (a pasted screenshot often arrives as "blob" with no extension).
        mime = (content_type or "").split(";")[0].strip().lower()
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/") or mime == "video/mp4":
            return "voice"
        if mime:
            return "file"
        return "file"

    stripped = (text or "").strip()
    if not stripped:
        return "empty"
    if _BARE_URL_RE.match(stripped) or _BARE_DOMAIN_RE.match(stripped):
        return "link"
    return "text"


def _extract_one(*, filename: str, content: bytes, content_type: str | None) -> dict:
    """Store one uploaded file and pull its text out."""
    source = detect_source(filename=filename, content_type=content_type)
    if source == "image":
        return store_and_describe(filename=filename, content=content)
    if source == "voice":
        return store_and_transcribe(filename=filename, content=content)
    return store_and_extract(filename=filename, content=content)


def capture(
    *,
    text: str | None = None,
    filename: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Ingest whatever was given, choosing the source type automatically.

    `files` is a list of {filename, content, content_type}. Several files plus
    a note become ONE entry with several attachments: three screenshots and a
    paragraph about a project describe one thing, and splitting them into
    separate entries would lose that.
    """
    uploads = list(files or [])
    if content is not None:
        uploads.append({"filename": filename or "upload", "content": content, "content_type": content_type})

    stripped = (text or "").strip()

    if uploads:
        return _capture_files(stripped, uploads)

    if not stripped:
        raise ValueError("Nothing to capture -- type something, or drop in a file")

    if detect_source(text=stripped) == "link":
        url = stripped if stripped.lower().startswith(("http://", "https://")) else f"https://{stripped}"
        try:
            return ingest_link(url)
        except ValueError:
            # Not fetchable (dead link, paywall, no readable article). Keeping
            # the URL as a note is better than losing the capture entirely.
            return ingest_text(stripped)

    return ingest_text(stripped)


def _capture_files(note: str, uploads: list[dict]) -> dict:
    extracted = [
        _extract_one(
            filename=upload.get("filename") or "upload",
            content=upload["content"],
            content_type=upload.get("content_type"),
        )
        for upload in uploads
    ]

    # The organizer only sees text, so each file's extraction is labelled with
    # its filename -- that's what lets one entry describe three screenshots
    # and still say which is which.
    parts = []
    if note:
        parts.append(note)
    for item in extracted:
        label = item["original_filename"] or item["source_type"]
        parts.append(f"[{item['source_type']}: {label}]\n{item['text']}")
    raw_text = "\n\n".join(parts).strip()

    kinds = {item["source_type"] for item in extracted}
    primary = extracted[0]
    source_type = primary["source_type"] if len(kinds) == 1 else "file"

    if len(extracted) == 1:
        hint = f"This is content from an uploaded {primary['source_type']} named '{primary['original_filename']}'."
    else:
        hint = (
            f"This entry has {len(extracted)} attachments "
            f"({', '.join(sorted(kinds))}) that all describe the same thing"
            + (", plus a note the user typed alongside them." if note else ".")
        )

    return create_entry(
        source_type=source_type,
        raw_text=raw_text,
        source_hint=hint,
        file_path=primary["file_path"],
        original_filename=primary["original_filename"],
        metadata={"attachment_count": len(extracted)},
        attachments=extracted,
    )
