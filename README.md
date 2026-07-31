# Lifelog

A personal AI assistant: dump in notes, links, files, photos, or voice memos, and
it automatically organizes everything (title, summary, category, tags, plus
type-specific fields like a recipe's ingredients or a subscription's renewal
date). One capture can be several things at once — an account, a subscription
and a reminder — and each becomes its own queryable record, so dated things
come back to you on the **agenda** instead of disappearing. Later, ask
questions in plain English and it searches your own saved data to answer — or
explore a 3D graph of how everything connects.

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
  `data/storage/` folder on your machine. The only thing that leaves is the
  text/images sent to whichever model provider you've configured.
- **Provider-agnostic** — Claude, OpenAI, Gemini, Grok, or DeepSeek, switchable
  at runtime. See [Model providers](#model-providers).
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

Edit `.env` and set a key for whichever provider you want to use — e.g.
`ANTHROPIC_API_KEY=sk-ant-...` from [platform.claude.com](https://platform.claude.com).
Any of Claude, OpenAI, Gemini, Grok, or DeepSeek works; see
[Model providers](#model-providers) for the full list and their env vars.

`LIFELOG_PROVIDER` and `LIFELOG_MODEL` set the defaults, and both are
switchable at runtime on the `/system` page. Leaving `LIFELOG_MODEL` blank
uses the provider's own default (`claude-opus-5` for Anthropic) — set
`claude-sonnet-5` or `claude-haiku-4-5` to cut cost on high volumes.

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
  main.py              Routes: ingestion, library, ask, skills, facets, agenda, graph
  db.py                SQLite schema (entries + facets), FTS5 search index, CRUD
  organize.py          Two-pass Claude call: route to skills, then extract them all
  facets.py            Builds/normalizes facet rows from each skill's extraction
  agenda.py            What's overdue/due/upcoming, and recurring spend
  settings.py          Runtime settings (defaults in code, overrides in the DB)
  selfmod.py           Self-modification: authors skills, runs the coding agent
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
    agenda/              What's overdue, due today, and upcoming (+ monthly spend)
    ask/                 Ask a question over your saved entries
    graph/               3D force-directed knowledge graph (lazy-loaded, client-only)
    skills/               Read-only view of whatever's in the backend's skills/ dir
    system/               Self-modification settings + the modification job queue
  components/           Shared UI (EntryCard, EntryDetail, Modal, Graph3D, VoiceRecorder, ...)
  lib/                  API client + shared types
```

## Dynamic skills (nothing hardcoded)

Every entry goes through two Claude calls, both driven entirely by files on
disk rather than logic in Python:

1. **Route to skills.** `skills.skills_menu()` scans `skills/*.md`, and Claude
   is shown only each skill's `{id, description}` -- a cheap, low-effort call
   (progressive disclosure, the same principle behind Claude's Agent Skills).
   It returns *every* skill that applies, not one.
2. **Extract them all in one pass.** Each selected skill's full instructions
   and `extra_schema` are merged into a single request, with the skills' fields
   nested under `facets.<skill_id>` so one reading of the content fills all of
   them while keeping the records separate.

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
  when_due:
    type: ["string", "null"]
    description: ISO 8601 date, or null.
promote:                         # optional -- see Facets below
  due_at: when_due
---
Any extra instructions for how to fill in the fields above.
```

Nothing needs to be registered anywhere else -- the file is picked up on the
very next request. The `/skills` page in the frontend reflects exactly what's
on disk. Sixteen skills ship by default: `general`, `article-link`, `recipe`,
`task`, `meeting-notes`, `idea`, `journal`, `contact`, `receipt-expense`,
`account`, `subscription`, `reminder`, `event`, `project`, `document`, and
`feature-request` (which is how the app extends itself — see
[Self-modification](#self-modification)).

Note that every field in an `extra_schema` is required in the generated JSON
schema, so anything optional must be nullable (`type: ["string", "null"]`) --
otherwise the model is forced to invent a value.

## Facets: one capture, several records

A single note is often several things at once. "Subscribed to Notion with
x@gmail.com, $10/month on the HDFC card, renews the 5th -- remind me before
it does" is an **account**, a **subscription**, and a **reminder**, and each
is queried differently later ("which email did I use for Notion", "what am I
paying monthly", "what's coming up").

So each skill that fires produces a **facet** row against the entry. The
skill's full extraction is kept verbatim in the facet's `data` blob, and a
skill can `promote:` some of its fields into shared columns:

| Column | Meaning | Promoted from, e.g. |
|--------|---------|---------------------|
| `due_at` | When it comes due | a task's `due_date`, a subscription's `next_renewal`, a document's `expires_on` |
| `amount` / `currency` | What it costs | a subscription's `cost`, a receipt's `amount` |
| `cadence` | How often it recurs | a subscription's `billing_period` |
| `identity` | Which account it's under | an account's `account_identifier` |
| `vendor` | Who it's with | a service, merchant, or issuer |

That's what makes one query span every kind. `GET /api/agenda` reads `due_at`
without knowing which skills produce dates, so **a new skill reaches the
agenda purely by declaring `promote: {due_at: ...}` in its frontmatter** --
no Python change. Values are normalized on the way in (dates, amounts,
currencies, billing periods); anything unparseable is dropped from its column
rather than stored in a form that would silently break a query, and the
original always survives in `data`.

Today's date is sent with every organize call, so "tomorrow", "next Friday"
and "renews on the 5th" resolve to real dates.

### The agenda

`GET /api/agenda?days=30` groups open, dated facets into **overdue**, **due
today**, and **upcoming**. The `/agenda` page renders that with a
recurring-spend total (normalized to a monthly figure, kept separate per
currency since there are no exchange rates here), and Done/Dismiss buttons
that `PATCH /api/facets/{id}` to take an item off the list.

`GET /api/facets?kind=subscription` browses one kind at a time.

The same applies to prompts: `prompts/organize_base.md`, `ask_system.md`,
`skill_selector.md`, and `image_describe.md` are plain text, loaded fresh on
every request -- edit tone, persona, or instructions without touching code.

## Model providers

Everything that talks to a model goes through [`app/llm.py`](app/llm.py), so
the provider is a setting on `/system`, not a code change.

| Provider | Key env var | Structured output | Images |
|----------|-------------|-------------------|--------|
| `anthropic` | `ANTHROPIC_API_KEY` | enforced schema | yes |
| `openai` | `OPENAI_API_KEY` | enforced schema | yes |
| `gemini` | `GEMINI_API_KEY` | enforced schema | yes |
| `grok` | `XAI_API_KEY` | enforced schema | yes |
| `deepseek` | `DEEPSEEK_API_KEY` | JSON only, shape not enforced | no |

**Keys are read from the environment only.** They are never written to the
database and never returned by the API — the UI is told whether a key is
present, never what it is.

The app depends heavily on structured output, and that's the thing that
actually differs between providers. Where a provider can't enforce a schema
server-side, the schema is written into the system prompt instead and the
response is parsed leniently (markdown fences, prose around the object), so a
weaker provider degrades in quality rather than breaking. Image capture on a
provider without vision fails with a clear message instead of a confusing API
error.

### Custom endpoints

`Custom API base URL` points a provider at a gateway, reseller, proxy, or a
local server that speaks the same protocol — for example an
Anthropic-compatible gateway that isn't `api.anthropic.com`, or a local
OpenAI-compatible server.

It is stored **per provider**, so switching provider can't send requests to
the wrong API.

Whoever operates that endpoint sees everything you capture — which, in this
app, means account emails, spending, and personal documents. Only point it at
something you'd trust with that.

## Self-modification

The assistant can extend itself. Say "it should also track my car servicing"
in a note and the `feature-request` skill files a **modification job** — or
request one directly on the `/system` page.

**A request always becomes a job, whatever the settings say.** The settings
decide only whether it runs now or waits as `pending` for you to run by hand,
so turning self-modification off loses nothing; it just puts you in the loop.

Two tiers, because the risk isn't comparable:

| | **skill** | **code** |
|---|---|---|
| What it does | Writes a `skills/*.md` file | Runs a coding agent against the source |
| Executes code? | No — data only | Yes |
| Default | Auto-runs once self-modification is on | Always waits for you, unless separately opted in |

A generated skill is validated by the same parser that loads skills before
it's written: kebab-case name matching its frontmatter, known `applies_to`
values, `promote` columns that exist and point at real fields, no overwriting
an existing skill, and a resolved path that can't leave `skills/`.

A code change requires a **clean git tree** (so your uncommitted work is never
swept into the agent's commit), runs on its own `selfmod/<id>-<slug>` branch,
commits there, and returns you to the branch you started on whatever happens.
**Nothing is ever merged for you** — review with
`git diff master..selfmod/<id>-<slug>` and merge yourself.

Settings (all on `/system`, stored in the database):

| Setting | Default | Meaning |
|---------|---------|---------|
| `self_modification_enabled` | off | Master switch. Off means everything waits for you. |
| `self_modification_auto_skill` | on | Let it write skill files by itself (once the master switch is on). |
| `self_modification_auto_code` | off | Let it change code without asking. |
| `agent_command` | `claude` | The CLI to invoke; use a full path if it isn't on PATH. The prompt is appended as `-p <prompt>`, without a shell. |
| `agent_timeout_seconds` | 900 | How long the agent may run. |

Note that a code job edits files while the app is running, so a dev server
with `--reload` will restart mid-job. The job returns you to your original
branch when it finishes, so the final state is whatever you had before.

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
