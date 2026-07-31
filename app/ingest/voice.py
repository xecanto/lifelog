import uuid
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import AUDIO_DIR, WHISPER_MODEL_SIZE
from app.ingest.common import create_entry

_ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    # Downloads the model from Hugging Face on first use (needs internet once),
    # then runs fully locally/offline from the local cache.
    return WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")


def transcribe(path: Path) -> str:
    model = _get_model()
    segments, _info = model.transcribe(str(path), beam_size=5)
    return " ".join(segment.text.strip() for segment in segments).strip()


def ingest_voice(*, filename: str, content: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio type '{ext}'. Supported: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = AUDIO_DIR / stored_name
    stored_path.write_bytes(content)

    try:
        try:
            transcript = transcribe(stored_path)
        except Exception as exc:
            raise ValueError(f"Could not transcribe this audio file: {exc}") from exc

        if not transcript:
            raise ValueError("Could not transcribe any speech from this audio")

        return create_entry(
            source_type="voice",
            raw_text=transcript,
            source_hint=f"This is a transcript of a voice memo named '{filename}'.",
            file_path=stored_path.relative_to(AUDIO_DIR.parent.parent).as_posix(),
            original_filename=filename,
            metadata={"extension": ext},
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
