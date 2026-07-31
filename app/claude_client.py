import os
from functools import lru_cache

import anthropic

from app.config import ANTHROPIC_API_KEY


class MissingAPIKeyError(RuntimeError):
    """Raised when no Anthropic credentials are configured at all."""


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    if ANTHROPIC_API_KEY:
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # No explicit key -- only proceed if the SDK has something else to fall
    # back to (ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile). Otherwise
    # give a clear, actionable error instead of the SDK's generic one.
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN") and not os.environ.get("ANTHROPIC_PROFILE"):
        config_dir = os.environ.get("ANTHROPIC_CONFIG_DIR", "~/.config/anthropic")
        has_profile = os.path.isdir(os.path.expanduser(config_dir))
        if not has_profile:
            raise MissingAPIKeyError(
                "No Anthropic API key configured. Copy .env.example to .env, set "
                "ANTHROPIC_API_KEY=sk-ant-..., and restart the server."
            )

    return anthropic.Anthropic()


def first_text(content_blocks) -> str:
    for block in content_blocks:
        if block.type == "text":
            return block.text
    return ""
