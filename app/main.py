import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db, llm, selfmod, settings, skills
from app.agenda import build_agenda, spend_summary
from app.clarify import apply_answers, with_questions
from app.claude_client import MissingAPIKeyError
from app.config import AGENDA_DEFAULT_DAYS, CORS_ORIGINS, DATA_DIR
from app.llm import LLMError
from app.reflect import reflect
from app.graph import build_graph
from app.ingest.capture import capture
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
    # A code job edits the source this server may be watching, so a reload can
    # kill the thread running it. Anything still marked `running` in a fresh
    # process is orphaned -- fail it so it doesn't sit there forever.
    db.reconcile_running_jobs()


def _handle(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except MissingAPIKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model provider error: {exc.message}")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="Could not reach the model provider. Check your internet connection.")


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


class ClarifyIn(BaseModel):
    """Free-text answers keyed by field name, e.g. {"cost": "ten a month"}."""

    answers: dict[str, str]


@app.post("/api/capture")
async def add_capture(
    text: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """One endpoint for anything: typed text, a URL, files, images, or audio.

    The source type is worked out from the input rather than chosen by the
    user, and several files plus a note become one entry -- see
    app/ingest/capture.py.
    """
    uploads = [
        {"filename": f.filename, "content": await f.read(), "content_type": f.content_type}
        # An empty file input still posts a part with no filename.
        for f in files
        if f is not None and f.filename
    ]
    entry = _handle(capture, text=text, files=uploads)
    # Anything a skill wanted but couldn't extract comes back as a question,
    # so the user is asked while the context is still fresh.
    return with_questions(entry)


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
    return with_questions(entry)


@app.post("/api/facets/{facet_id}/clarify")
def clarify_facet(facet_id: int, payload: ClarifyIn) -> dict:
    """Answer the follow-up questions for one record.

    Answers are free text; they're interpreted through the skill's own field
    definitions so promoted columns stay in the shape queries expect.
    """
    if not db.get_facet(facet_id):
        raise HTTPException(status_code=404, detail="Facet not found")
    facet = _handle(apply_answers, facet_id=facet_id, answers=payload.answers)
    entry = with_questions(db.get_entry(facet["entry_id"]))
    return {"facet": facet, "entry": entry}


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
# Facets -- the structured records extracted from entries (subscriptions,
# accounts, reminders, ...). One entry can produce several.
# ---------------------------------------------------------------------------


class FacetStatusIn(BaseModel):
    status: str


@app.get("/api/agenda")
def get_agenda(days: int = AGENDA_DEFAULT_DAYS) -> dict:
    if days < 0 or days > 3650:
        raise HTTPException(status_code=400, detail="days must be between 0 and 3650")
    return build_agenda(days)


@app.get("/api/facets")
def get_facets(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    facets = db.list_facets(kind=kind, status=status, limit=limit, offset=offset)
    return {"facets": facets, "spend": spend_summary(facets)}


@app.get("/api/facet-kinds")
def get_facet_kinds() -> dict:
    return {"kinds": db.list_facet_kinds()}


@app.patch("/api/facets/{facet_id}")
def update_facet(facet_id: int, payload: FacetStatusIn) -> dict:
    try:
        updated = db.set_facet_status(facet_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Facet not found")
    facet = db.get_facet(facet_id)
    db.log_event(
        kind="facet_action",
        entry_id=facet["entry_id"],
        data={"facet_id": facet_id, "kind": facet["kind"], "status": payload.status},
    )
    return facet


# ---------------------------------------------------------------------------
# Settings and self-modification
#
# A modification request always becomes a job. The settings decide only
# whether it runs now or waits as `pending` for the user to run by hand.
# ---------------------------------------------------------------------------


class SettingsIn(BaseModel):
    values: dict[str, object]


class ModificationIn(BaseModel):
    prompt: str
    title: str = ""
    kind: str = "code"


@app.get("/api/settings")
def get_settings() -> dict:
    return {"settings": settings.describe()}


@app.patch("/api/settings")
def patch_settings(payload: SettingsIn) -> dict:
    try:
        settings.set_many(payload.values)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"settings": settings.describe()}


@app.get("/api/providers")
def get_providers() -> dict:
    """Available model providers and whether each has a key configured.

    Key *values* are never returned -- only whether one is present.
    """
    return {
        "providers": llm.describe_providers(),
        "active": {"provider": llm.active_provider().id, "model": llm.active_model()},
    }


@app.get("/api/system")
def get_system_status() -> dict:
    return selfmod.status()


@app.get("/api/modifications")
def get_modifications(status: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    return {"jobs": db.list_jobs(status=status, limit=limit, offset=offset)}


@app.get("/api/modifications/{job_id}")
def get_modification(job_id: int) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/modifications")
def create_modification(payload: ModificationIn) -> dict:
    return _handle(
        selfmod.create_request,
        title=payload.title,
        prompt=payload.prompt,
        kind=payload.kind,
    )


@app.post("/api/modifications/{job_id}/run")
def run_modification(job_id: int) -> dict:
    """Run a pending job now, regardless of the auto-run settings.

    This is the manual path: the user looked at the prompt and chose to run
    it, which is a stronger signal than any setting.
    """
    if not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return _handle(selfmod.start_job, job_id)


@app.post("/api/modifications/{job_id}/cancel")
def cancel_modification(job_id: int) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Only pending jobs can be cancelled (this one is {job['status']})")
    db.update_job(job_id, status="cancelled", finished_at=db.now_iso())
    return db.get_job(job_id)


# ---------------------------------------------------------------------------
# Activity and reflection -- learning from how the app is actually used
# ---------------------------------------------------------------------------


@app.get("/api/activity")
def get_activity(limit: int = 50) -> dict:
    return {
        "events": db.list_events(limit=limit),
        "counts": db.count_events_by_kind(),
    }


@app.post("/api/reflect")
def run_reflection(dry_run: bool = False) -> dict:
    """Review usage and file proposals for what's missing.

    Proposals become ordinary modification jobs, so the self-modification
    settings decide whether they run or wait. `dry_run` proposes without
    filing anything.
    """
    return _handle(reflect, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@app.get("/api/graph")
def get_graph() -> dict:
    return build_graph()
