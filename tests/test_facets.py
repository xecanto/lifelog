"""Facet normalization and construction.

The rule under test throughout: a value that can't be normalized is dropped
from its column rather than stored in a shape that would silently break a
query. The original always survives in `data`.
"""

import pytest

from app.facets import (
    build_facet,
    monthly_cost,
    normalize_amount,
    normalize_cadence,
    normalize_currency,
    normalize_date,
)
from app.skills import Skill


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-08-05", "2026-08-05"),
        ("2026-08-05T09:30", "2026-08-05T09:30"),
        ("renews 2026-08-05 next", "2026-08-05"),
        ("2026-13-45", None),      # impossible date
        ("sometime soon", None),   # unparseable -- must not reach due_at
        ("", None),
        (None, None),
        (12345, None),
    ],
)
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("$10.99", 10.99), (10, 10.0), ("1,200 INR", 1200.0), ("n/a", None), (None, None), (True, None)],
)
def test_normalize_amount(value, expected):
    assert normalize_amount(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("$", "USD"), ("usd", "USD"), ("₹", "INR"), ("", None), (None, None)],
)
def test_normalize_currency(value, expected):
    assert normalize_currency(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("per month", "monthly"),
        ("billed annually", "yearly"),
        ("every 3 months", "quarterly"),
        ("every 2 weeks", "biweekly"),   # must beat the bare "week" alias
        ("every two weeks", "biweekly"),
        ("lifetime", "one-time"),
        ("whenever", None),
    ],
)
def test_normalize_cadence(value, expected):
    assert normalize_cadence(value) == expected


def test_monthly_cost_puts_cadences_on_one_footing():
    assert monthly_cost(120, "yearly") == 10.0
    assert monthly_cost(10, "monthly") == 10.0
    assert monthly_cost(30, "quarterly") == 10.0
    assert monthly_cost(50, "one-time") == 0.0
    assert monthly_cost(None, "monthly") is None


SUBSCRIPTION = Skill(
    id="subscription",
    description="",
    extra_schema={"service": {}, "cost": {}, "billing_period": {}, "next_renewal": {}},
    promote={
        "vendor": "service",
        "amount": "cost",
        "cadence": "billing_period",
        "due_at": "next_renewal",
    },
)


def test_promoted_fields_reach_their_columns():
    facet = build_facet(
        SUBSCRIPTION,
        {
            "label": "Notion Plus",
            "service": "Notion",
            "cost": "$10",
            "billing_period": "per month",
            "next_renewal": "2026-08-05",
        },
    )
    assert facet["kind"] == "subscription"
    assert facet["label"] == "Notion Plus"
    assert facet["vendor"] == "Notion"
    assert facet["amount"] == 10.0
    assert facet["cadence"] == "monthly"
    assert facet["due_at"] == "2026-08-05"
    # The raw extraction is preserved untouched.
    assert facet["data"]["cost"] == "$10"


def test_unparseable_promoted_value_is_dropped_not_stored():
    facet = build_facet(SUBSCRIPTION, {"label": "x", "service": "Notion", "next_renewal": "soon-ish"})
    assert facet["due_at"] is None
    assert facet["data"]["next_renewal"] == "soon-ish"


def test_priced_subscription_without_a_period_assumed_monthly():
    facet = build_facet(SUBSCRIPTION, {"label": "x", "service": "N", "cost": 10})
    assert facet["cadence"] == "monthly"


def test_facet_with_no_meaningful_fields_is_dropped():
    """A label alone is model-written summary text, not information."""
    assert build_facet(SUBSCRIPTION, {"label": "Something", "service": None, "cost": None}) is None
    assert build_facet(SUBSCRIPTION, {}) is None


def test_unknown_promote_column_is_ignored_not_fatal():
    skill = Skill(id="x", description="", extra_schema={"f": {}}, promote={"nonsense": "f", "vendor": "f"})
    facet = build_facet(skill, {"label": "l", "f": "value"})
    assert facet["vendor"] == "value"
    assert "nonsense" not in facet
