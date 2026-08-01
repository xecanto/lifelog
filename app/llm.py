"""One interface over several model providers.

Everything in the app that talks to a model goes through `complete_json` or
`describe_image` here, so switching provider is a setting rather than a code
change.

Two transports cover all of them:

- **Anthropic**, via the official SDK, using native structured output.
- **OpenAI-compatible** (OpenAI, DeepSeek, xAI/Grok, Gemini's compat
  endpoint), via plain HTTP. They differ only in base URL, key, and how much
  structured output they support.

Structured output is the thing that actually varies, and the app depends on
it heavily, so each provider declares what it supports:

- `schema`      -- enforces a full JSON schema server-side.
- `json_object` -- guarantees valid JSON but not the shape.
- `prompt`      -- no guarantee at all.

For anything below `schema` the schema is also written into the system prompt
and the response is parsed leniently, so a weaker provider degrades in
quality rather than breaking outright.

API keys are read from the environment only. They are never stored in the
database and never returned by the API -- the UI is told whether a key is
present, never what it is.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from app import settings
from app.claude_client import MissingAPIKeyError, first_text

_TIMEOUT = 120.0


class LLMError(RuntimeError):
    """A provider call failed in a way worth showing the user."""


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    default_model: str
    # Env vars checked in order; the first one set wins.
    api_key_env: tuple[str, ...]
    # "anthropic" (native SDK) or "openai" (chat/completions over HTTP).
    transport: str
    # "schema" | "json_object" | "prompt" -- see the module docstring.
    structured: str
    vision: bool
    base_url: str = ""
    # Models known to work well here; the UI offers these but any id is valid.
    suggested_models: tuple[str, ...] = field(default_factory=tuple)


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="anthropic",
        label="Claude (Anthropic)",
        default_model="claude-opus-5",
        api_key_env=("ANTHROPIC_API_KEY",),
        transport="anthropic",
        structured="schema",
        vision=True,
        suggested_models=("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"),
    ),
    ProviderSpec(
        id="openai",
        label="OpenAI",
        default_model="gpt-4o",
        api_key_env=("OPENAI_API_KEY",),
        transport="openai",
        structured="schema",
        vision=True,
        base_url="https://api.openai.com/v1",
        suggested_models=("gpt-4o", "gpt-4o-mini"),
    ),
    ProviderSpec(
        id="gemini",
        label="Gemini (Google)",
        default_model="gemini-2.0-flash",
        api_key_env=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        transport="openai",
        structured="schema",
        vision=True,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        suggested_models=("gemini-2.0-flash", "gemini-2.0-pro"),
    ),
    ProviderSpec(
        id="grok",
        label="Grok (xAI)",
        default_model="grok-2-latest",
        api_key_env=("XAI_API_KEY", "GROK_API_KEY"),
        transport="openai",
        structured="schema",
        vision=True,
        base_url="https://api.x.ai/v1",
        suggested_models=("grok-2-latest", "grok-2-vision-latest"),
    ),
    ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        default_model="deepseek-chat",
        api_key_env=("DEEPSEEK_API_KEY",),
        transport="openai",
        # DeepSeek guarantees valid JSON but not a specific shape, so the
        # schema goes in the prompt and the result is validated on our side.
        structured="json_object",
        vision=False,
        base_url="https://api.deepseek.com/v1",
        suggested_models=("deepseek-chat", "deepseek-reasoner"),
    ),
)

BY_ID = {p.id: p for p in PROVIDERS}
PROVIDER_IDS = tuple(p.id for p in PROVIDERS)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def active_provider() -> ProviderSpec:
    chosen = str(settings.get("llm_provider") or "anthropic")
    return BY_ID.get(chosen, BY_ID["anthropic"])


def active_model(spec: ProviderSpec | None = None) -> str:
    spec = spec or active_provider()
    configured = str(settings.get("llm_model") or "").strip()
    return configured or spec.default_model


def api_key_for(spec: ProviderSpec) -> str | None:
    for name in spec.api_key_env:
        value = os.environ.get(name)
        if value:
            return value
    return None


def active_base_url(spec: ProviderSpec | None = None) -> str:
    """The endpoint to call, honouring a configured override.

    An override lets the app talk to a gateway, reseller, proxy, or a local
    server that speaks the same protocol -- e.g. an Anthropic-compatible
    gateway that isn't api.anthropic.com.
    """
    spec = spec or active_provider()
    override = str(settings.get("llm_base_url") or "").strip()
    return (override or spec.base_url).rstrip("/")


@lru_cache(maxsize=4)
def _anthropic_client(api_key: str, base_url: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, base_url=base_url or None)


def describe_providers() -> list[dict]:
    """Provider metadata for the UI. Never includes key values."""
    current = active_provider()
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "default_model": spec.default_model,
            "suggested_models": list(spec.suggested_models),
            "api_key_env": list(spec.api_key_env),
            "has_key": api_key_for(spec) is not None,
            "structured_output": spec.structured,
            "vision": spec.vision,
            "active": spec.id == current.id,
            "base_url": active_base_url(spec) if spec.id == current.id else spec.base_url,
        }
        for spec in PROVIDERS
    ]


def _require_key(spec: ProviderSpec) -> str:
    key = api_key_for(spec)
    if not key:
        raise MissingAPIKeyError(
            f"No API key for {spec.label}. Set {spec.api_key_env[0]} in .env and restart the server."
        )
    return key


# ---------------------------------------------------------------------------
# JSON parsing -- lenient, because not every provider enforces a schema
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\s*\n(.*?)\n?```\s*$", re.DOTALL)


def parse_json_loosely(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise LLMError("The model returned an empty response")

    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Some models prepend a sentence before the object. Take the outermost
        # {...} span and try that.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("The model did not return JSON")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"The model returned malformed JSON: {exc}")

    if not isinstance(data, dict):
        raise LLMError("The model returned JSON that wasn't an object")
    return data


def _schema_instructions(schema: dict) -> str:
    return (
        "\n\nRespond with a single JSON object and nothing else -- no prose, no "
        "markdown fences. It must conform exactly to this JSON schema, including "
        "every required field:\n"
        f"{json.dumps(schema, indent=2)}"
    )


# ---------------------------------------------------------------------------
# Text -> JSON
# ---------------------------------------------------------------------------


def complete_json(
    *,
    system: str,
    user_content: str,
    schema: dict,
    max_tokens: int = 2048,
    effort: str = "medium",
    schema_name: str = "response",
) -> dict | None:
    """Ask the active provider for JSON matching `schema`.

    Returns the parsed object, or None if the model refused. Raises LLMError
    for anything else that went wrong.
    """
    spec = active_provider()
    model = active_model(spec)

    if spec.transport == "anthropic":
        return _anthropic_json(spec, model, system, user_content, schema, max_tokens, effort)
    return _openai_json(spec, model, system, user_content, schema, max_tokens, schema_name)


def _anthropic_json(spec, model, system, user_content, schema, max_tokens, effort) -> dict | None:
    import anthropic

    client = _anthropic_client(_require_key(spec), active_base_url(spec))
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            output_config={
                "format": {"type": "json_schema", "schema": schema},
                "effort": effort,
            },
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIStatusError as exc:
        raise LLMError(f"{spec.label} error: {exc.message}")
    except anthropic.APIConnectionError:
        raise LLMError(f"Could not reach {spec.label}. Check your internet connection.")

    if response.stop_reason == "refusal":
        return None
    return parse_json_loosely(first_text(response.content))


def _openai_json(spec, model, system, user_content, schema, max_tokens, schema_name) -> dict | None:
    system_prompt = system
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [],
    }

    if spec.structured == "schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
    elif spec.structured == "json_object":
        body["response_format"] = {"type": "json_object"}
        system_prompt += _schema_instructions(schema)
    else:
        system_prompt += _schema_instructions(schema)

    body["messages"] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    data = _post_openai(spec, body)
    message = _first_choice(data)
    if message.get("refusal"):
        return None
    return parse_json_loosely(message.get("content") or "")


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------


def describe_image(*, prompt: str, media_type: str, b64_data: str, max_tokens: int = 1024) -> str | None:
    """Describe an image with the active provider. None means it refused."""
    spec = active_provider()
    model = active_model(spec)

    if not spec.vision:
        raise LLMError(
            f"{spec.label} can't process images. Switch provider on the System page, "
            "or save this as a file instead."
        )

    if spec.transport == "anthropic":
        import anthropic

        client = _anthropic_client(_require_key(spec), active_base_url(spec))
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
        except anthropic.APIStatusError as exc:
            raise LLMError(f"{spec.label} error: {exc.message}")
        except anthropic.APIConnectionError:
            raise LLMError(f"Could not reach {spec.label}. Check your internet connection.")

        if response.stop_reason == "refusal":
            return None
        return first_text(response.content)

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64_data}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    data = _post_openai(spec, body)
    message = _first_choice(data)
    if message.get("refusal"):
        return None
    return message.get("content") or ""


# ---------------------------------------------------------------------------
# OpenAI-compatible transport
# ---------------------------------------------------------------------------


def _post_openai(spec: ProviderSpec, body: dict) -> dict:
    key = _require_key(spec)
    url = f"{active_base_url(spec)}/chat/completions"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach {spec.label}: {exc}")

    if response.status_code >= 400:
        raise LLMError(f"{spec.label} error ({response.status_code}): {_error_message(response)}")

    try:
        return response.json()
    except ValueError:
        raise LLMError(f"{spec.label} returned a non-JSON response")


def _error_message(response: httpx.Response) -> str:
    """Pull a human-readable message out of an error body.

    Shapes differ: OpenAI returns {"error": {...}}, Google returns a *list*
    of those. Anything unrecognized falls back to raw text -- an unhelpful
    message beats an exception thrown while reporting an exception, which
    hides the real failure.
    """
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]

    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return str(payload)[:300]

    error = payload.get("error", payload)
    if isinstance(error, dict):
        return str(error.get("message") or error)[:300]
    return str(error)[:300]


def _first_choice(data: dict) -> dict:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("The provider returned no choices")
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        raise LLMError("The provider returned an unexpected message shape")
    return message
