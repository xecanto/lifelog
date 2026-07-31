# Lifelog

A personal AI assistant: dump in notes, links, files, photos, or voice memos, and
it automatically organizes everything (title, summary, category, tags, plus
type-specific fields like a recipe's ingredients or a task's due date). Later,
ask it questions in plain English and it searches your own saved data to answer
— or explore a 3D graph of how everything connects.

Two processes, run together in local dev:

- **`app/`** — a Python/FastAPI backend. Owns the SQLite database, file
  ingestion (PDF/Word/text parsing, article extraction, local Whisper
  transcription), the Claude calls, and the knowledge graph computation.
- **`web/`** — a Next.js (App Router) frontend. Talks to the backend over
  plain REST (`NEXT_PUBLIC_API_URL`). Nothing frontend-specific lives in the
  backend and vice versa — you could point a different frontend at the same
  API.

## Design choices

- **Local-first storage** — everything lives in a SQLite database and a
  `data/storage/` folder on your machine. Nothing is sent anywhere except the
  text/images that are processed by the Claude API.
- **Nothing is hardcoded** — see [Dynamic skills](#dynamic-skills-nothing-hardcoded) below. The
  system prompts live under `prompts/*.md`, and the "skills" that decide how
  each entry gets organized live under `skills/*.md`. Both are read from disk
  on every request — edit or add a file and it takes effect immediately, no
  code change or restart.
- **Local, offline speech-to-text** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  for voice memos — audio never leaves your machine.
- **No vector database** — text search uses SQLite's built-in full-text index
  (FTS5); the knowledge graph's "these are about the same thing" edges use
  TF-IDF cosine similarity (scikit-learn). Claude does the semantic reasoning
  on top of whatever gets retrieved. This is plenty for a personal knowledge
  base and keeps the dependency footprint small (no embedding model, no
  vector DB service).

## What it can ingest

| Type  | How |
|-------|-----|
| Text  | Paste or type directly |
| Links | Give it a URL — it fetches and extracts the readable article text |
| Files | PDF, Word (`.docx`), plain text/Markdown/CSV |
| Images | Claude describes the image so it becomes searchable text |
| Voice | Record in the browser or upload an audio file — transcribed locally |

## Setup

### 1. Backend (`app/`)

```sh
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

copy .env.example .env      # Windows
# cp .env.example .env        # macOS/Linux
```

Edit `.env` and set `ANTHROPIC_API_KEY=sk-ant-...`. Get a key at
[platform.claude.com](https://platform.claude.com).

By default the app uses `claude-opus-5` for organizing and answering. If
you're processing a lot of entries and want to cut cost, set
`LIFELOG_MODEL=claude-sonnet-5` or `claude-haiku-4-5` in `.env`.

Run it:

```sh
.venv\Scripts\uvicorn app.main:app --reload
```

The API is now at **http://127.0.0.1:8000**. The SQLite database and file
storage are created automatically under `data/` on first run.

### 2. Frontend (`web/`)

In a second terminal:

```sh
cd web
npm install
copy .env.local.example .env.local   # Windows
# cp .env.local.example .env.local     # macOS/Linux
npm run dev
```

Open **http://localhost:3000**. `.env.local` just needs to point
`NEXT_PUBLIC_API_URL` at wherever the backend is running (defaults to
`http://127.0.0.1:8000`, which matches step 1 above).

## Notes on voice memos

The first time you transcribe audio, faster-whisper downloads a small model
(~75–150 MB depending on `LIFELOG_WHISPER_MODEL`) from Hugging Face and caches
it locally. After that, transcription runs fully offline. If you want higher
accuracy at the cost of speed, set `LIFELOG_WHISPER_MODEL=small` or `medium`
in `.env`.

## Project layout

```
app/                 FastAPI backend
  main.py              Routes: ingestion, library, ask, skills, graph
  db.py                SQLite schema, FTS5 search index, CRUD
  organize.py          Two-pass Claude call: pick a skill, then extract with it
  search.py            Ask: FTS5 retrieval + Claude answer with citations
  graph.py             Builds the knowledge graph (entries + tags + TF-IDF edges)
  skills.py            Loads skills/*.md from disk (no hardcoded skill list)
  prompts.py           Loads prompts/*.md from disk (no hardcoded prompt strings)
  claude_client.py     Anthropic client helper
  ingest/               One module per source type (text, files, links, images, voice)
skills/                Skill definitions (markdown + YAML frontmatter) -- see below
prompts/               System prompts (plain markdown, editable)
data/                  SQLite DB + uploaded files (git-ignored, created at runtime)

web/                  Next.js frontend (App Router)
  app/
    add/                 /add/{text,link,file,image,voice} -- one real route per capture type
    library/             /library list + /library/[id] full-page entry detail
    @modal/(.)library/[id]/  Intercepted route: same URL, rendered as a modal when
                              navigated to from inside the app (proper back-stack --
                              browser Back closes the modal instead of leaving the page)
    ask/                 Ask a question over your saved entries
    graph/               3D force-directed knowledge graph (lazy-loaded, client-only)
    skills/               Read-only view of whatever's in the backend's skills/ dir
  components/           Shared UI (EntryCard, EntryDetail, Modal, Graph3D, VoiceRecorder, ...)
  lib/                  API client + shared types
```

## Dynamic skills (nothing hardcoded)

Every entry goes through two Claude calls, both driven entirely by files on
disk rather than logic in Python:

1. **Select a skill.** `skills.skills_menu()` scans `skills/*.md`, and Claude
   is shown only each skill's `{id, description}` -- a cheap, low-effort call
   (progressive disclosure, the same principle behind Claude's Agent Skills).
2. **Extract with it.** Once a skill is picked, its full instructions and
   `extra_schema` (skill-specific structured fields) are merged into the
   request. A recipe skill asks for `ingredients`/`steps`; a task skill asks
   for `due_date`/`priority`; a general fallback just asks for the universal
   title/summary/category/tags.

To add a new skill, create `skills/my-skill.md`:

```markdown
---
name: my-skill
description: When Claude should pick this skill over the others.
applies_to: [text, voice]        # which source types this applies to
extra_schema:
  some_field:
    type: string
    description: What Claude should put here.
---
Any extra instructions for how to fill in the fields above.
```

Nothing needs to be registered anywhere else -- the file is picked up on the
very next request. The `/skills` page in the frontend reflects exactly what's
on disk. Nine skills ship by default (`general`, `article-link`, `recipe`,
`task`, `meeting-notes`, `idea`, `journal`, `contact`, `receipt-expense`).

The same applies to prompts: `prompts/organize_base.md`, `ask_system.md`,
`skill_selector.md`, and `image_describe.md` are plain text, loaded fresh on
every request -- edit tone, persona, or instructions without touching code.

## The knowledge graph

`GET /api/graph` returns every entry plus every tag shared by 2+ entries as
nodes, with two kinds of edges:

- **Entry → tag**, for every tag on that entry.
- **Entry → entry**, when two entries' text is similar enough (TF-IDF cosine
  similarity over title + summary + content, capped to each entry's top
  neighbors so the graph stays readable).

The `/graph` page renders this with `react-force-graph-3d` (three.js under
the hood), lazy-loaded via `next/dynamic` so the ~1MB three.js bundle is only
downloaded when you actually open the page. Click a topic (tag) node to dim
everything except what's connected to it -- "show me everything around this
topic." Click an entry node to open it (as the same backstack-aware modal
used everywhere else in the app).

## How search ("Ask") works

`/ask` runs a keyword search (SQLite FTS5) over your saved entries, hands the
top candidates to Claude along with your question, and Claude answers using
only that context -- citing which entries it actually used as `sources`.
