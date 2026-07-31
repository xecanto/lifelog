"""Runtime settings, editable from the UI.

Defaults live here; the database only ever stores values that have been
changed away from their default. That way a new setting added in code
appears immediately with a sensible value instead of needing a migration.

The self-modification switches are deliberately conservative. A modification
request always becomes a job row either way -- the switches decide only
whether it runs now or waits for you.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app import db


@dataclass(frozen=True)
class SettingSpec:
    key: str
    default: Any
    type: type
    label: str
    description: str
    # When set, the UI offers these values. Held as a callable because the
    # provider list lives in app/llm.py, which imports this module.
    choices: Callable[[], list[str]] | None = None
    # Stored separately per provider. An endpoint override only makes sense
    # for the provider it was entered for -- carrying one global value across
    # a provider switch would send requests to the wrong API.
    per_provider: bool = False
    # For per-provider settings, the provider this spec's default belongs to.
    # An env-supplied default describes one configuration, so it must not
    # apply to providers it wasn't written for.
    default_provider: str | None = None


def _provider_ids() -> list[str]:
    from app.llm import PROVIDER_IDS

    return list(PROVIDER_IDS)


SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        key="llm_provider",
        default=os.environ.get("LIFELOG_PROVIDER", "anthropic"),
        type=str,
        label="Model provider",
        description=(
            "Which API the assistant thinks with. Each provider's key is read from the "
            "environment -- keys are never stored here. Providers differ in whether they "
            "can enforce a response schema and whether they can read images."
        ),
        choices=_provider_ids,
    ),
    SettingSpec(
        key="llm_model",
        default=os.environ.get("LIFELOG_MODEL", ""),
        type=str,
        label="Model",
        description="Model id to use with the selected provider. Leave blank for that provider's default.",
    ),
    SettingSpec(
        key="llm_base_url",
        default=os.environ.get("LIFELOG_BASE_URL", ""),
        type=str,
        label="Custom API base URL",
        description=(
            "Point this provider at a different endpoint -- a gateway, reseller, proxy, or "
            "local server. Saved per provider, so switching provider won't send requests to "
            "the wrong API. Leave blank to use the provider's own. Whoever runs that "
            "endpoint sees everything you capture."
        ),
        per_provider=True,
        default_provider=os.environ.get("LIFELOG_PROVIDER", "anthropic"),
    ),
    SettingSpec(
        key="self_modification_enabled",
        default=False,
        type=bool,
        label="Enable self-modification",
        description=(
            "Master switch. When off, every modification request is saved as a pending "
            "job for you to run by hand -- nothing is lost, nothing runs on its own."
        ),
    ),
    SettingSpec(
        key="self_modification_auto_skill",
        default=True,
        type=bool,
        label="Auto-run new skills",
        description=(
            "When self-modification is on, let the assistant write new skill files by "
            "itself. Skills are data, not code: nothing is executed, the file is "
            "validated before it's written, and it can only land in skills/."
        ),
    ),
    SettingSpec(
        key="self_modification_auto_code",
        default=False,
        type=bool,
        label="Auto-run code changes",
        description=(
            "When self-modification is on, let a coding agent edit the app without "
            "asking first. This runs a real agent against your source. Changes always "
            "land on their own git branch and are never merged for you, but leaving "
            "this off means you approve each change before it runs."
        ),
    ),
    SettingSpec(
        key="agent_command",
        default=os.environ.get("LIFELOG_AGENT_COMMAND", "claude"),
        type=str,
        label="Coding agent command",
        description=(
            "The CLI invoked for code changes. The prompt is appended as `-p <prompt>`. "
            "Use a full path if it isn't on PATH."
        ),
    ),
    SettingSpec(
        key="agent_timeout_seconds",
        default=900,
        type=int,
        label="Agent timeout (seconds)",
        description="How long a code-change agent may run before it's killed.",
    ),
)

BY_KEY = {spec.key: spec for spec in SPECS}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    if spec.type is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ValueError(f"'{spec.key}' expects a boolean, got {raw!r}")
    if spec.type is int:
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValueError(f"'{spec.key}' expects a number, got {raw!r}")
    return str(raw)


def _resolve(spec: SettingSpec, overrides: dict[str, str], provider: str) -> Any:
    stored_key = f"{spec.key}::{provider}" if spec.per_provider else spec.key
    if stored_key in overrides:
        try:
            return _coerce(spec, overrides[stored_key])
        except ValueError:
            pass  # a corrupt stored value shouldn't break the app
    if spec.per_provider and spec.default_provider and provider != spec.default_provider:
        return spec.type()  # e.g. "" -- the default was for another provider
    return spec.default


def current_provider(overrides: dict[str, str] | None = None) -> str:
    """The selected provider, which scopes the per-provider settings."""
    overrides = db.get_setting_overrides() if overrides is None else overrides
    spec = BY_KEY["llm_provider"]
    return str(_resolve(spec, overrides, ""))


def get_all() -> dict[str, Any]:
    overrides = db.get_setting_overrides()
    provider = current_provider(overrides)
    return {spec.key: _resolve(spec, overrides, provider) for spec in SPECS}


def get(key: str) -> Any:
    if key not in BY_KEY:
        raise KeyError(f"Unknown setting '{key}'")
    return get_all()[key]


def set_many(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - set(BY_KEY)
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")

    coerced = {key: _coerce(BY_KEY[key], value) for key, value in updates.items()}

    for key, value in coerced.items():
        spec = BY_KEY[key]
        if spec.choices:
            allowed = spec.choices()
            if value not in allowed:
                raise ValueError(f"'{key}' must be one of: {', '.join(allowed)}")

    # A provider change in the same request scopes the per-provider keys, so
    # resolve the target provider before writing anything.
    provider = str(coerced.get("llm_provider") or current_provider())

    for key, value in coerced.items():
        spec = BY_KEY[key]
        stored_key = f"{key}::{provider}" if spec.per_provider else key
        stored = "true" if value is True else "false" if value is False else str(value)
        db.set_setting_override(stored_key, stored)
    return get_all()


def describe() -> list[dict]:
    """Settings plus their metadata, for rendering a settings UI."""
    values = get_all()
    provider = str(values["llm_provider"])
    return [
        {
            "key": spec.key,
            "value": values[spec.key],
            "default": spec.default,
            "type": spec.type.__name__,
            # Make the scope visible: this field means something different
            # once you switch provider.
            "label": f"{spec.label} ({provider})" if spec.per_provider else spec.label,
            "description": spec.description,
            "choices": spec.choices() if spec.choices else None,
        }
        for spec in SPECS
    ]


def should_auto_run(kind: str) -> bool:
    """Whether a job of this kind may start on its own.

    The master switch gates both tiers; the per-tier switch then decides.
    Anything not explicitly allowed waits as a pending job.
    """
    values = get_all()
    if not values["self_modification_enabled"]:
        return False
    if kind == "skill":
        return bool(values["self_modification_auto_skill"])
    if kind == "code":
        return bool(values["self_modification_auto_code"])
    return False
