import base64
import uuid
from pathlib import Path

from app import llm
from app.config import IMAGES_DIR
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

        described = llm.describe_image(
            prompt=load_prompt("image_describe"),
            media_type=media_type,
            b64_data=b64,
            max_tokens=1024,
        )
        if described is None:
            description = "(The model declined to describe this image.)"
        else:
            description = described or "(No description could be generated for this image.)"

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
