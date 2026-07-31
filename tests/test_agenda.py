"""Agenda bucketing and recurring-spend totals."""

from datetime import date, timedelta

import pytest

from app import db
from app.agenda import build_agenda, spend_summary

TODAY = date.today()


@pytest.fixture
def entry_id():
    return db.insert_entry(
        source_type="text", title="Source note", raw_text="x", summary="",
        category="Admin", tags=[], skill="subscription",
    )


def add_facet(entry_id, kind, due=None, **kwargs):
    return db.insert_facet(entry_id=entry_id, kind=kind, label=f"{kind} item", due_at=due, **kwargs)


def test_buckets_by_day_not_by_kind(entry_id):
    add_facet(entry_id, "document", due=(TODAY - timedelta(days=4)).isoformat())
    add_facet(entry_id, "reminder", due=TODAY.isoformat())
    add_facet(entry_id, "subscription", due=(TODAY + timedelta(days=12)).isoformat())

    agenda = build_agenda(30)

    assert agenda["counts"] == {"overdue": 1, "due_today": 1, "upcoming": 1}
    assert agenda["overdue"][0]["kind"] == "document"
    assert agenda["due_today"][0]["kind"] == "reminder"


def test_a_timestamped_due_date_still_lands_on_the_right_day(entry_id):
    """Dates are compared on their YYYY-MM-DD prefix, so both forms work."""
    add_facet(entry_id, "event", due=f"{TODAY.isoformat()}T15:00")
    assert build_agenda(30)["counts"]["due_today"] == 1


def test_overdue_is_not_bounded_by_the_window(entry_id):
    add_facet(entry_id, "task", due=(TODAY - timedelta(days=400)).isoformat())
    assert build_agenda(7)["counts"]["overdue"] == 1


def test_items_beyond_the_window_are_excluded(entry_id):
    add_facet(entry_id, "task", due=(TODAY + timedelta(days=60)).isoformat())
    assert build_agenda(30)["counts"]["upcoming"] == 0
    assert build_agenda(90)["counts"]["upcoming"] == 1


def test_undated_facets_never_appear(entry_id):
    add_facet(entry_id, "account")
    agenda = build_agenda(30)
    assert agenda["counts"] == {"overdue": 0, "due_today": 0, "upcoming": 0}


def test_acting_on_an_item_takes_it_off_the_agenda(entry_id):
    facet_id = add_facet(entry_id, "reminder", due=TODAY.isoformat())
    assert build_agenda(30)["counts"]["due_today"] == 1

    db.set_facet_status(facet_id, "done")
    assert build_agenda(30)["counts"]["due_today"] == 0


def test_agenda_rows_carry_their_entry(entry_id):
    add_facet(entry_id, "reminder", due=TODAY.isoformat())
    row = build_agenda(30)["due_today"][0]
    assert row["entry_title"] == "Source note"
    assert row["entry_category"] == "Admin"


def test_invalid_status_is_rejected(entry_id):
    facet_id = add_facet(entry_id, "reminder")
    with pytest.raises(ValueError):
        db.set_facet_status(facet_id, "banana")


def test_spend_normalizes_cadences_to_a_monthly_figure():
    summary = spend_summary([
        {"amount": 10, "cadence": "monthly", "currency": "USD"},
        {"amount": 120, "cadence": "yearly", "currency": "USD"},
    ])
    assert summary["monthly_by_currency"] == {"USD": 20.0}
    assert summary["counted"] == 2


def test_currencies_are_kept_apart_never_summed():
    """There are no exchange rates here; a mixed total would be a lie."""
    summary = spend_summary([
        {"amount": 10, "cadence": "monthly", "currency": "USD"},
        {"amount": 800, "cadence": "monthly", "currency": "INR"},
    ])
    assert summary["monthly_by_currency"] == {"USD": 10.0, "INR": 800.0}


def test_unpriced_subscriptions_are_counted_separately():
    summary = spend_summary([{"amount": None, "cadence": "monthly", "currency": "USD"}])
    assert summary["unpriced"] == 1
    assert summary["monthly_by_currency"] == {}
