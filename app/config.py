from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lifelog.db"
STORAGE_DIR = DATA_DIR / "storage"
IMAGES_DIR = STORAGE_DIR / "images"
FILES_DIR = STORAGE_DIR / "files"
AUDIO_DIR = STORAGE_DIR / "audio"

# User-editable, hot-reloaded from disk -- nothing in here is hardcoded in
# Python. Add a new .md file to SKILLS_DIR or edit a file in PROMPTS_DIR and
# it takes effect on the next request, no restart needed.
SKILLS_DIR = BASE_DIR / "skills"
PROMPTS_DIR = BASE_DIR / "prompts"

for d in (DATA_DIR, STORAGE_DIR, IMAGES_DIR, FILES_DIR, AUDIO_DIR, SKILLS_DIR, PROMPTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("LIFELOG_MODEL", "claude-opus-5")
WHISPER_MODEL_SIZE = os.environ.get("LIFELOG_WHISPER_MODEL", "base")

# Comma-separated list of origins allowed to call the API (the Next.js dev
# server by default).
CORS_ORIGINS = [o.strip() for o in os.environ.get("LIFELOG_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# Minimum cosine similarity (TF-IDF) for two entries to be linked in the graph.
GRAPH_SIMILARITY_THRESHOLD = float(os.environ.get("LIFELOG_GRAPH_THRESHOLD", "0.15"))
# Max similarity edges per entry, to keep the graph readable.
GRAPH_MAX_NEIGHBORS = 5

# Max characters of raw text sent to Claude when organizing an entry.
# The full text is always stored and searched locally; this only bounds
# the cost of the one-time organize call.
ORGANIZE_TEXT_LIMIT = 12000

# How many candidate entries to pull from full-text search before handing
# them to Claude to answer a question.
SEARCH_CANDIDATE_LIMIT = 12
# How many characters of each candidate's raw text to include in context.
SEARCH_SNIPPET_LIMIT = 2000
