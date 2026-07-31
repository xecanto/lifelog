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

from app.ingest.files import TEXT_EXTENSIONS
from app.ingest.files import ingest_file
from app.ingest.images import ingest_image
from app.ingest.links import ingest_link
from app.ingest.text import ingest_text
from app.ingest.voice import ingest_voice

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


def capture(
    *,
    text: str | None = None,
    filename: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
) -> dict:
    """Ingest whatever was given, choosing the source type automatically."""
    source = detect_source(text=text, filename=filename, content_type=content_type)

    if source == "empty":
        raise ValueError("Nothing to capture -- type something, or drop in a file")

    if source in ("image", "voice", "file"):
        if content is None:
            raise ValueError("No file content was uploaded")
        name = filename or "upload"
        if source == "image":
            return ingest_image(filename=name, content=content)
        if source == "voice":
            return ingest_voice(filename=name, content=content)
        return ingest_file(filename=name, content=content)

    stripped = (text or "").strip()
    if source == "link":
        url = stripped if stripped.lower().startswith(("http://", "https://")) else f"https://{stripped}"
        try:
            return ingest_link(url)
        except ValueError:
            # Not fetchable (dead link, paywall, no readable article). Keeping
            # the URL as a note is better than losing the capture entirely.
            return ingest_text(stripped)

    return ingest_text(stripped)
