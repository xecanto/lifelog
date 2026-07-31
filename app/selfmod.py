"""Self-modification: the app changing itself in response to a request.

Every request becomes a job row, always. The settings only decide whether it
runs now or waits as `pending` for you to run by hand -- so turning
self-modification off loses nothing, it just puts a human in the loop.

Two tiers, because they carry very different risk:

- **skill** -- writes a `skills/*.md` file. Data only: no code executes, the
  file is validated by the same parser that loads skills, the name must be a
  fresh slug, and it can only ever land inside `skills/`. Safe to auto-run.
- **code** -- hands the prompt to a coding agent that edits the source. This
  is arbitrary code execution on your machine, so it requires a clean git
  tree, works on its own branch, commits there, and returns you to the branch
  you started on. Nothing is ever merged for you.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from app import db, settings, skills
from app.claude_client import first_text, get_client
from app.config import BASE_DIR, MODEL, SKILLS_DIR
from app.facets import PROMOTABLE_COLUMNS
from app.prompts import load_prompt

VALID_SOURCE_TYPES = {"text", "link", "file", "image", "voice"}
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Agent output can be long; keep the tail, which is where the summary is.
_MAX_RESULT_CHARS = 8000

SKILL_AUTHOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "kebab-case id for the new skill; must match the `name` in the frontmatter.",
        },
        "file_content": {
            "type": "string",
            "description": "The complete skill markdown file, starting with the --- frontmatter block.",
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences on what this skill captures that existing skills don't.",
        },
    },
    "required": ["name", "file_content", "reasoning"],
    "additionalProperties": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str, fallback: str = "change") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug or fallback)[:40]


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def _truncate(text: str) -> str:
    text = text or ""
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return f"...(truncated)...\n{text[-_MAX_RESULT_CHARS:]}"


# ---------------------------------------------------------------------------
# Creating requests
# ---------------------------------------------------------------------------


def create_request(
    *,
    title: str,
    prompt: str,
    kind: str = "code",
    origin: str = "manual",
    entry_id: int | None = None,
    run_now: bool | None = None,
) -> dict:
    """Record a modification request, and start it if settings allow.

    `run_now` overrides the settings -- that's the manual "run this pending
    job" path, which is an explicit human decision.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("A modification request needs a prompt")

    job_id = db.insert_job(
        title=(title or "").strip() or prompt[:80],
        prompt=prompt,
        kind=kind,
        origin=origin,
        entry_id=entry_id,
    )

    should_run = settings.should_auto_run(kind) if run_now is None else run_now
    if should_run:
        start_job(job_id)

    return db.get_job(job_id)


def start_job(job_id: int) -> dict:
    """Claim a pending job and run it on a background thread."""
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    if not db.claim_job(job_id):
        raise ValueError(f"Job {job_id} is '{job['status']}', not pending")

    thread = threading.Thread(target=_execute, args=(job_id,), daemon=True)
    thread.start()
    return db.get_job(job_id)


def _execute(job_id: int) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    try:
        runner = _run_skill_job if job["kind"] == "skill" else _run_code_job
        result = runner(job)
        db.update_job(job_id, status="succeeded", result=_truncate(result), finished_at=_now())
    except Exception as exc:  # any failure must land on the job, not vanish
        db.update_job(job_id, status="failed", error=_truncate(str(exc)), finished_at=_now())


# ---------------------------------------------------------------------------
# Tier 1: authoring a skill (data only)
# ---------------------------------------------------------------------------


def validate_skill_file(name: str, content: str) -> tuple[str, skills.Skill]:
    """Validate an authored skill file. Raises ValueError with the reason.

    Everything here is a refusal to write something the loader would later
    choke on, or that would escape skills/.
    """
    name = (name or "").strip()
    if not _SLUG_RE.match(name):
        raise ValueError(f"Skill name '{name}' must be kebab-case (letters, digits, single hyphens)")

    skill = skills.parse_skill_text(content or "")
    if skill is None:
        raise ValueError("Generated file has no valid YAML frontmatter block")
    if skill.id != name:
        raise ValueError(f"Frontmatter name '{skill.id}' does not match file name '{name}'")
    if not skill.description.strip():
        raise ValueError("Skill needs a description -- it's what routing selects on")

    if skills.get_skill(name) is not None:
        raise ValueError(f"A skill named '{name}' already exists; edit it by hand instead of overwriting it")

    bad_sources = set(skill.applies_to) - VALID_SOURCE_TYPES
    if bad_sources:
        raise ValueError(f"Unknown applies_to value(s): {', '.join(sorted(bad_sources))}")

    if not isinstance(skill.extra_schema, dict):
        raise ValueError("extra_schema must be a mapping of field name -> field definition")
    for field, definition in skill.extra_schema.items():
        if not isinstance(definition, dict) or "type" not in definition:
            raise ValueError(f"extra_schema field '{field}' needs at least a `type`")

    if not isinstance(skill.promote, dict):
        raise ValueError("promote must be a mapping of column -> field name")
    for column, field in skill.promote.items():
        if column not in PROMOTABLE_COLUMNS:
            raise ValueError(
                f"promote column '{column}' is not one of: {', '.join(PROMOTABLE_COLUMNS)}"
            )
        if field not in skill.extra_schema:
            raise ValueError(f"promote maps '{column}' to '{field}', which isn't in extra_schema")

    # Belt and braces: the name is already a strict slug, so this can't fail,
    # but a path that escapes skills/ must never be writable from a model.
    target = (SKILLS_DIR / f"{name}.md").resolve()
    if target.parent != SKILLS_DIR.resolve():
        raise ValueError("Refusing to write a skill outside the skills directory")

    return name, skill


def _run_skill_job(job: dict) -> str:
    existing = "\n".join(f"- {s.id}: {s.description}" for s in skills.list_skills())

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=load_prompt("skill_author"),
        output_config={
            "format": {"type": "json_schema", "schema": SKILL_AUTHOR_SCHEMA},
            "effort": "medium",
        },
        messages=[
            {
                "role": "user",
                "content": (
                    f"Existing skills:\n{existing}\n\n"
                    f"Request:\n\"\"\"\n{job['prompt']}\n\"\"\""
                ),
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise ValueError("The model declined to write this skill")

    try:
        data = json.loads(first_text(response.content))
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Could not parse the authored skill file")

    name, skill = validate_skill_file(data.get("name", ""), data.get("file_content", ""))
    path = SKILLS_DIR / f"{name}.md"
    path.write_text(data["file_content"], encoding="utf-8")

    # The work is done at this point -- nothing below may raise, or a job that
    # actually succeeded would be recorded as failed.
    promoted = ", ".join(f"{k} <- {v}" for k, v in skill.promote.items()) or "none"
    return (
        f"Created skill '{name}' at {_display_path(path)}\n"
        f"Reasoning: {data.get('reasoning', '').strip()}\n"
        f"Fields: {', '.join(skill.extra_schema) or 'none'}\n"
        f"Promoted columns: {promoted}\n"
        f"Applies to: {', '.join(skill.applies_to)}\n\n"
        f"{data['file_content']}"
    )


# ---------------------------------------------------------------------------
# Tier 2: code changes via a coding agent
# ---------------------------------------------------------------------------


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def _agent_argv(prompt: str) -> list[str]:
    """Build argv for the coding agent.

    The command is split without a shell and the prompt is passed as its own
    argument, so nothing in the prompt can be interpreted as shell syntax.
    """
    command = str(settings.get("agent_command")).strip()
    if not command:
        raise ValueError("No coding agent command configured (see Settings)")
    parts = [p.strip('"') for p in shlex.split(command, posix=False)]
    if not parts:
        raise ValueError("Coding agent command is empty")
    return [*parts, "-p", prompt]


def preflight_code() -> list[str]:
    """Reasons a code job can't run right now. Empty means good to go."""
    problems: list[str] = []
    try:
        _git("rev-parse", "--is-inside-work-tree")
    except (ValueError, FileNotFoundError):
        problems.append("Not a git repository -- run `git init` first so changes can be undone")
        return problems

    if _git("status", "--porcelain"):
        problems.append(
            "The working tree has uncommitted changes. Commit or stash them first, "
            "otherwise your edits get swept into the agent's commit."
        )
    return problems


def _run_code_job(job: dict) -> str:
    problems = preflight_code()
    if problems:
        raise ValueError(" ".join(problems))

    original_branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = f"selfmod/{job['id']}-{_slugify(job['title'])}"
    argv = _agent_argv(job["prompt"])
    timeout = int(settings.get("agent_timeout_seconds"))

    _git("checkout", "-b", branch)
    db.update_job(job["id"], branch=branch)

    try:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise ValueError(
                f"Coding agent '{argv[0]}' not found. Set the correct command in Settings."
            )
        except subprocess.TimeoutExpired:
            raise ValueError(f"The coding agent exceeded its {timeout}s timeout and was stopped")

        changed = _git("status", "--porcelain")
        if changed:
            _git("add", "-A")
            _git("commit", "-m", f"Self-modification #{job['id']}: {job['title']}")
            diffstat = _git("diff", "--stat", f"{original_branch}..HEAD")
        else:
            diffstat = ""

        output = _truncate((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))
        if proc.returncode != 0 and not changed:
            raise ValueError(f"Agent exited with code {proc.returncode} and changed nothing.\n\n{output}")

        if not changed:
            return f"Agent finished but made no changes.\n\n{output}"

        return (
            f"Changes committed on branch `{branch}` (not merged).\n"
            f"Review with: git diff {original_branch}..{branch}\n\n"
            f"{diffstat}\n\n--- agent output ---\n{output}"
        )
    finally:
        # Always put the working copy back where it was, so the running app
        # keeps serving the reviewed code no matter how the job ended.
        try:
            _git("checkout", "--force", original_branch)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Status, for the UI
# ---------------------------------------------------------------------------


def status() -> dict:
    values = settings.get_all()
    try:
        agent = _agent_argv("")[0]
        agent_found = Path(agent).exists() or _which(agent) is not None
    except ValueError:
        agent_found = False

    return {
        "settings": values,
        "counts": db.count_jobs_by_status(),
        "code_preflight": preflight_code(),
        "agent_available": agent_found,
    }


def _which(command: str):
    from shutil import which

    return which(command)
