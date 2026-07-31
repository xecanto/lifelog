import uuid
from pathlib import Path

import docx
from pypdf import PdfReader

from app.config import FILES_DIR
from app.ingest.common import create_entry

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log"}


def _extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _extract_docx(path: Path) -> str:
    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs if p.text]
    return "\n".join(paragraphs).strip()


def _extract_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def ingest_file(*, filename: str, content: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in TEXT_EXTENSIONS and ext not in (".pdf", ".docx"):
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: .pdf, .docx, .txt, .md, .csv, .log"
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = FILES_DIR / stored_name
    stored_path.write_bytes(content)

    try:
        if ext == ".pdf":
            raw_text = _extract_pdf(stored_path)
        elif ext == ".docx":
            raw_text = _extract_docx(stored_path)
        else:
            raw_text = _extract_text_file(stored_path)

        if not raw_text:
            raise ValueError("Could not extract any text from this file")

        return create_entry(
            source_type="file",
            raw_text=raw_text,
            source_hint=f"This is text extracted from an uploaded file named '{filename}'.",
            file_path=stored_path.relative_to(FILES_DIR.parent.parent).as_posix(),
            original_filename=filename,
            metadata={"extension": ext},
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
