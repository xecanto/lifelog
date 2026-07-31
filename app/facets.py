"""Turns a skill's raw extraction into a storable, queryable facet row.

A facet is one *thing* a capture is about. A single voice memo -- "subscribed
to Notion with x@gmail.com, $10/mo, renews the 5th, remind me before it" --
produces three: an account, a subscription, and a reminder.

The skill's full extraction is kept verbatim in the facet's `data` blob. On
top of that, a skill can `promote:` some of its fields into the shared
columns on the facets table (`due_at`, `amount`, `identity`, ...), which is
what lets one query span every kind -- "what's due this week" doesn't care
whether the date came from a task's `due_date`, a subscription's
`next_renewal`, or an event's `starts_at`.

Everything here is defensive: a model-produced value that can't be
normalized is dropped from its column rather than being stored in a form
that would poison a query. The original value always survives in `data`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.skills import Skill

# Injected into every facet's schema so each one can name itself for the UI
# ("Notion Plus -- $10/mo") without every skill author remembering to.
LABEL_FIELD = "label"
LABEL_SCHEMA = {
    "type": "string",
    "description": (
        "A short human-readable label for this specific item, 2-6 words, "
        "specific enough to recognize in a list (e.g. 'Notion Plus - $10/mo', "
        "'Renew passport', 'GitHub account (work email)')."
    ),
}

PROMOTABLE_COLUMNS = ("due_at", "cadence", "amount", "currency", "identity", "vendor")

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_TIME_RE = re.compile(r"[T ](\d{2}):(\d{2})")
_AMOUNT_RE = re.compile(r"-?\d+(?:[\d,]*\d)?(?:\.\d+)?")

_CADENCE_ALIASES = {
    "day": "daily", "daily": "daily", "per day": "daily",
    "week": "weekly", "weekly": "weekly", "per week": "weekly",
    "fortnight": "biweekly", "fortnightly": "biweekly", "biweekly": "biweekly",
    "bi-weekly": "biweekly", "every two weeks": "biweekly", "every 2 weeks": "biweekly",
    "month": "monthly", "monthly": "monthly", "per month": "monthly", "mo": "monthly",
    "quarter": "quarterly", "quarterly": "quarterly", "per quarter": "quarterly",
    "every three months": "quarterly", "every 3 months": "quarterly",
    "year": "yearly", "yearly": "yearly", "annual": "yearly", "annually": "yearly",
    "per year": "yearly", "yr": "yearly",
    "once": "one-time", "one time": "one-time", "one-time": "one-time",
    "lifetime": "one-time", "single": "one-time",
}

# Longest alias first, so "every 2 weeks" resolves to biweekly instead of
# matching the bare "week" inside it.
_CADENCE_BY_SPECIFICITY = sorted(_CADENCE_ALIASES.items(), key=lambda kv: -len(kv[0]))

# How many times a cadence bills per month -- used to put subscriptions on a
# common footing for a spend total.
_PER_MONTH = {
    "daily": 30.0,
    "weekly": 52 / 12,
    "biweekly": 26 / 12,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "yearly": 1 / 12,
    "one-time": 0.0,
}

_CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY",
    "₹": "INR", "Rs": "INR", "Rs.": "INR", "₨": "INR",
    "₩": "KRW", "₽": "RUB", "R$": "BRL", "A$": "AUD", "C$": "CAD",
}


def normalize_date(value) -> str | None:
    """Coerce a model-supplied date to `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`.

    Anything without a recognizable ISO date is dropped -- a due date that
    can't be compared is worse than no due date, because it silently never
    shows up on the agenda.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None

    time_match = _TIME_RE.search(text)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{parsed.isoformat()}T{hour:02d}:{minute:02d}"
    return parsed.isoformat()


def normalize_amount(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _AMOUNT_RE.search(value.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalize_currency(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[text]
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    letters = re.sub(r"[^A-Za-z]", "", text).upper()
    return letters[:3] if len(letters) >= 3 else None


def normalize_cadence(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if text in _CADENCE_ALIASES:
        return _CADENCE_ALIASES[text]
    # "every month", "billed monthly", "$10/month" -- find any alias inside,
    # allowing a trailing plural ("every 3 months").
    for alias, canonical in _CADENCE_BY_SPECIFICITY:
        if re.search(rf"\b{re.escape(alias)}s?\b", text):
            return canonical
    return None


def normalize_text(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


_NORMALIZERS = {
    "due_at": normalize_date,
    "amount": normalize_amount,
    "currency": normalize_currency,
    "cadence": normalize_cadence,
    "identity": normalize_text,
    "vendor": normalize_text,
}


def monthly_cost(amount: float | None, cadence: str | None) -> float | None:
    """Normalize a recurring cost to a per-month figure, for spend totals."""
    if amount is None:
        return None
    factor = _PER_MONTH.get(cadence or "monthly")
    if factor is None:
        return None
    return round(amount * factor, 2)


def build_facet(skill: Skill, data: dict) -> dict | None:
    """Build insert_facet kwargs from one skill's extraction.

    Returns None when the skill produced nothing worth storing, so an
    over-eager router pick doesn't litter the database with empty rows.
    """
    payload = dict(data or {})
    label = normalize_text(payload.pop(LABEL_FIELD, None)) or ""

    meaningful = {
        k: v for k, v in payload.items() if v not in (None, "", [], {})
    }
    if not meaningful and not label:
        return None

    facet = {"kind": skill.id, "label": label, "data": payload}

    for column, field_name in (skill.promote or {}).items():
        if column not in PROMOTABLE_COLUMNS:
            continue  # unknown column in a skill file -- ignore, don't crash
        normalizer = _NORMALIZERS[column]
        facet[column] = normalizer(payload.get(field_name))

    # A subscription that names a price but no billing period is almost
    # always monthly; assuming that beats leaving it out of spend totals.
    if facet.get("amount") is not None and "cadence" in (skill.promote or {}) and not facet.get("cadence"):
        facet["cadence"] = "monthly"

    return facet
