"""Loads system prompts from disk instead of hardcoding them in Python.

Edit any file under prompts/ and the change takes effect on the next
request -- no restart, no code change.
"""

from datetime import datetime

from app.config import PROMPTS_DIR


def today_context() -> str:
    """Today's date, for any prompt that has to resolve a relative date.

    Without this the model cannot turn "tomorrow", "next Friday" or "renews
    on the 5th" into a real date -- which is most of what makes a reminder
    or a renewal useful.
    """
    now = datetime.now().astimezone()
    return f"Today is {now.strftime('%A, %d %B %Y')} ({now.strftime('%Y-%m-%d')})."


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text(encoding="utf-8").strip()
