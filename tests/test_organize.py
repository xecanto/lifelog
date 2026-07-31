"""Multi-skill routing and extraction."""

from app import db
from app.ingest.common import create_entry
from app.organize import _build_schema, _derive_title, organize
from app.skills import get_skill


def test_schema_nests_each_selected_skill_separately():
    selected = [get_skill("subscription"), get_skill("reminder")]
    schema = _build_schema(selected)

    assert "facets" in schema["properties"]
    facets = schema["properties"]["facets"]["properties"]
    assert set(facets) == {"subscription", "reminder"}
    # Every field is required, so optional ones must be nullable -- otherwise
    # the model is forced to invent values.
    assert "next_renewal" in facets["subscription"]["properties"]
    assert facets["subscription"]["required"] == list(facets["subscription"]["properties"])
    # A label is injected into every facet without skill authors adding it.
    assert "label" in facets["reminder"]["properties"]


def test_skills_without_extra_fields_produce_no_facet_object():
    schema = _build_schema([get_skill("general")])
    assert "facets" not in schema["properties"]


def test_derive_title_never_cuts_mid_word():
    long_text = "Gym today: bench press 60kg 5x5, squats 80kg 3x8, felt strong and rested"
    title = _derive_title(long_text)
    assert len(title) <= 70
    assert long_text.startswith(title)
    assert not title.endswith(" ")
    assert _derive_title("") == "Untitled entry"
    assert _derive_title("  a\n\n  b  ") == "a b"


def test_one_capture_becomes_several_facets(stub_llm):
    stub_llm.returns(
        {"skill_ids": ["subscription", "account", "reminder"]},
        {
            "title": "Notion Plus",
            "summary": "Subscribed to Notion.",
            "category": "Finance",
            "tags": ["notion"],
            "facets": {
                "subscription": {
                    "label": "Notion Plus - $10/mo",
                    "service": "Notion Plus",
                    "cost": 10,
                    "currency": "USD",
                    "billing_period": "monthly",
                    "next_renewal": "2026-08-05",
                    "paid_with": "HDFC credit card",
                    "account_identifier": "me@example.com",
                },
                "account": {
                    "label": "Notion account",
                    "service": "Notion",
                    "account_identifier": "me@example.com",
                    "signup_method": None,
                    "platform": None,
                    "plan": "Plus",
                },
                "reminder": {
                    "label": "Notion renews soon",
                    "remind_about": "Cancel if unused",
                    "remind_on": "2026-08-02",
                    "lead_time": "3 days before",
                },
            },
        },
    )

    result = organize("Subscribed to Notion...", source_type="voice")

    assert result["skills"] == ["subscription", "account", "reminder"]
    assert result["skill"] == "subscription"
    kinds = {f["kind"]: f for f in result["facets"]}
    assert set(kinds) == {"subscription", "account", "reminder"}
    assert kinds["subscription"]["due_at"] == "2026-08-05"
    assert kinds["subscription"]["amount"] == 10.0
    assert kinds["reminder"]["due_at"] == "2026-08-02"
    assert kinds["account"]["identity"] == "me@example.com"


def test_empty_strings_from_the_model_are_treated_as_missing(stub_llm):
    """A blank title makes an entry unfindable, so empty must not pass through."""
    stub_llm.returns(
        {"skill_ids": ["journal"]},
        {"title": "", "summary": "", "category": "", "tags": ["", "  "], "facets": {"journal": {"label": "", "mood": None}}},
    )

    result = organize("Gym today: bench press 60kg 5x5, squats 80kg", source_type="text")

    assert result["title"].startswith("Gym today")
    assert result["category"] == "Other"
    assert result["tags"] == []
    assert result["facets"] == []  # nothing meaningful was extracted


def test_routing_failure_falls_back_to_general(stub_llm, monkeypatch):
    """Routing is a convenience -- `general` is a fine default, so a hiccup
    there shouldn't stop the capture."""
    from app import llm

    calls = {"n": 0}
    real = llm.complete_json

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.LLMError("provider down")
        return real(**kwargs)

    stub_llm.returns({"title": "t", "summary": "", "category": "Other", "tags": []})
    monkeypatch.setattr(llm, "complete_json", flaky)

    result = organize("some note", source_type="text")
    assert result["skill"] == "general"


def test_extraction_failure_propagates_rather_than_saving_junk(monkeypatch):
    """Extraction is the whole point, so a provider failure there must surface.

    The capture box keeps the user's text on error, so nothing is lost by
    failing loudly -- whereas silently storing an unorganized entry that
    *looks* organized is not recoverable.
    """
    import pytest

    from app import llm

    def boom(**kwargs):
        raise llm.LLMError("provider down")

    monkeypatch.setattr(llm, "complete_json", boom)
    with pytest.raises(llm.LLMError):
        organize("some note", source_type="text")


def test_today_is_sent_so_relative_dates_can_resolve(stub_llm):
    stub_llm.returns({"skill_ids": ["general"]}, {"title": "t", "summary": "", "category": "c", "tags": []})
    organize("note", source_type="text")
    assert "Today is" in stub_llm.calls[0]["user_content"]
    assert "Today is" in stub_llm.calls[1]["user_content"]


def test_create_entry_persists_facets_and_logs_the_capture(stub_llm):
    stub_llm.returns(
        {"skill_ids": ["task"]},
        {
            "title": "Renew passport",
            "summary": "",
            "category": "Admin",
            "tags": ["passport"],
            "facets": {"task": {"label": "Renew passport", "due_date": "2026-09-01", "priority": "high"}},
        },
    )

    entry = create_entry(source_type="text", raw_text="renew my passport by september")

    assert entry["facets"][0]["due_at"] == "2026-09-01"
    assert entry["metadata"]["skills"] == ["task"]
    assert [e["kind"] for e in db.list_events()] == ["capture"]


def test_deleting_an_entry_removes_its_facets(stub_llm):
    stub_llm.returns(
        {"skill_ids": ["task"]},
        {
            "title": "t", "summary": "", "category": "c", "tags": [],
            "facets": {"task": {"label": "l", "due_date": "2026-09-01", "priority": None}},
        },
    )
    entry = create_entry(source_type="text", raw_text="x")
    assert db.list_facets()

    db.delete_entry(entry["id"])
    assert db.list_facets() == []
