"""Loads system prompts from disk instead of hardcoding them in Python.

Edit any file under prompts/ and the change takes effect on the next
request -- no restart, no code change.
"""

from app.config import PROMPTS_DIR


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text(encoding="utf-8").strip()
