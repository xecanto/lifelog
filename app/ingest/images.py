import base64
import uuid
from pathlib import Path

from app.claude_client import first_text, get_client
from app.config import IMAGES_DIR, MODEL
from app.ingest.common import create_entry
from app.prompts import load_prompt

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def ingest_image(*, filename: str, content: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    media_type = _MEDIA_TYPES.get(ext)
    if not media_type:
        raise ValueError(f"Unsupported image type '{ext}'. Supported: png, jpg, jpeg, gif, webp")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = IMAGES_DIR / stored_name
    stored_path.write_bytes(content)

    try:
        b64 = base64.standard_b64encode(content).decode("utf-8")

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64},
                        },
                        {"type": "text", "text": load_prompt("image_describe")},
                    ],
                }
            ],
        )

        if response.stop_reason == "refusal":
            description = "(Claude declined to describe this image.)"
        else:
            description = first_text(response.content) or "(No description could be generated for this image.)"

        return create_entry(
            source_type="image",
            raw_text=description,
            source_hint=f"This is a description of an uploaded image named '{filename}'.",
            file_path=stored_path.relative_to(IMAGES_DIR.parent.parent).as_posix(),
            original_filename=filename,
            metadata={"extension": ext},
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
