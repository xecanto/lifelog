import anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db, skills
from app.claude_client import MissingAPIKeyError
from app.config import CORS_ORIGINS, DATA_DIR
from app.graph import build_graph
from app.ingest.files import ingest_file
from app.ingest.images import ingest_image
from app.ingest.links import ingest_link
from app.ingest.text import ingest_text
from app.ingest.voice import ingest_voice
from app.search import ask as ask_question

app = FastAPI(title="Lifelog API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves uploaded images/files/audio to the Next.js frontend, e.g.
# /media/images/xxxx.png
app.mount("/media", StaticFiles(directory=DATA_DIR / "storage"), name="media")


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()


def _handle(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="Could not reach the Claude API. Check your internet connection.")


@app.get("/")
def health() -> dict:
    return {"status": "ok", "app": "lifelog-api"}


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class TextIn(BaseModel):
    text: str


class LinkIn(BaseModel):
    url: str


class AskIn(BaseModel):
    question: str


@app.post("/api/entries/text")
def add_text(payload: TextIn) -> dict:
    return _handle(ingest_text, payload.text)


@app.post("/api/entries/link")
def add_link(payload: LinkIn) -> dict:
    return _handle(ingest_link, payload.url)


@app.post("/api/entries/file")
async def add_file(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    return _handle(ingest_file, filename=file.filename, content=content)


@app.post("/api/entries/image")
async def add_image(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    return _handle(ingest_image, filename=file.filename, content=content)


@app.post("/api/entries/voice")
async def add_voice(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    return _handle(ingest_voice, filename=file.filename, content=content)


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------


@app.get("/api/entries")
def get_entries(limit: int = 50, offset: int = 0, category: str | None = None) -> dict:
    entries = db.list_entries(limit=limit, offset=offset, category=category)
    return {"entries": entries, "total": db.count_entries()}


@app.get("/api/entries/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = db.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.delete("/api/entries/{entry_id}")
def remove_entry(entry_id: int) -> dict:
    entry = db.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.get("file_path"):
        try:
            full_path = DATA_DIR / entry["file_path"]
            if full_path.exists():
                full_path.unlink()
        except OSError:
            pass
    db.delete_entry(entry_id)
    return {"ok": True}


@app.get("/api/categories")
def get_categories() -> dict:
    return {"categories": db.list_categories()}


# ---------------------------------------------------------------------------
# Skills -- reflects exactly what's on disk under skills/, nothing hardcoded
# ---------------------------------------------------------------------------


@app.get("/api/skills")
def get_skills() -> dict:
    return {
        "skills": [
            {
                "id": s.id,
                "description": s.description,
                "applies_to": s.applies_to,
                "fields": list(s.extra_schema.keys()),
            }
            for s in skills.list_skills()
        ]
    }


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------


@app.post("/api/ask")
def ask(payload: AskIn) -> dict:
    return _handle(ask_question, payload.question)


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@app.get("/api/graph")
def get_graph() -> dict:
    return build_graph()
