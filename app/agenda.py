"""What's coming up, across every kind of facet.

A due date is a due date whether it came from a task's deadline, a
subscription's renewal, a passport's expiry, or an event's start time -- so
this queries the shared `due_at` column rather than knowing anything about
the skills that produced it. A new skill that promotes `due_at` shows up here
with no code change.
"""

from __future__ import annotations

from datetime import date, timedelta

from app import db
from app.config import AGENDA_DEFAULT_DAYS
from app.facets import monthly_cost


def _day_of(facet: dict) -> str:
    return (facet.get("due_at") or "")[:10]


def build_agenda(days: int = AGENDA_DEFAULT_DAYS) -> dict:
    today = date.today()
    horizon = today + timedelta(days=max(days, 0))
    today_str = today.isoformat()

    # No lower bound: something overdue since last month still matters.
    facets = db.list_due_facets(end=horizon.isoformat())

    overdue, due_today, upcoming = [], [], []
    for facet in facets:
        day = _day_of(facet)
        if day < today_str:
            overdue.append(facet)
        elif day == today_str:
            due_today.append(facet)
        else:
            upcoming.append(facet)

    return {
        "today": today_str,
        "window_days": days,
        "overdue": overdue,
        "due_today": due_today,
        "upcoming": upcoming,
        "counts": {
            "overdue": len(overdue),
            "due_today": len(due_today),
            "upcoming": len(upcoming),
        },
    }


def spend_summary(facets: list[dict]) -> dict:
    """Recurring cost of a set of facets, normalized to a monthly figure.

    Currencies are kept apart rather than converted -- there are no exchange
    rates here, and a total that silently mixed USD and INR would be a lie.
    """
    by_currency: dict[str, float] = {}
    unpriced = 0

    for facet in facets:
        per_month = monthly_cost(facet.get("amount"), facet.get("cadence"))
        if per_month is None:
            unpriced += 1
            continue
        currency = facet.get("currency") or "unknown"
        by_currency[currency] = round(by_currency.get(currency, 0.0) + per_month, 2)

    return {
        "monthly_by_currency": by_currency,
        "counted": len(facets) - unpriced,
        "unpriced": unpriced,
    }
