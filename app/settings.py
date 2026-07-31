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
    # Free-text settings that shouldn't be rendered as a checkbox/number.
    secret: bool = False


SPECS: tuple[SettingSpec, ...] = (
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


def get_all() -> dict[str, Any]:
    overrides = db.get_setting_overrides()
    values: dict[str, Any] = {}
    for spec in SPECS:
        if spec.key in overrides:
            try:
                values[spec.key] = _coerce(spec, overrides[spec.key])
                continue
            except ValueError:
                pass  # a corrupt stored value shouldn't break the app
        values[spec.key] = spec.default
    return values


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
        stored = "true" if value is True else "false" if value is False else str(value)
        db.set_setting_override(key, stored)
    return get_all()


def describe() -> list[dict]:
    """Settings plus their metadata, for rendering a settings UI."""
    values = get_all()
    return [
        {
            "key": spec.key,
            "value": values[spec.key],
            "default": spec.default,
            "type": spec.type.__name__,
            "label": spec.label,
            "description": spec.description,
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
