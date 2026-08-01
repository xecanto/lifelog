"""Updating an existing record instead of creating a duplicate.

The dangerous failure here is a *wrong* merge: a duplicate row is easy to
spot and delete, but silently folding two different things together corrupts
a record the user relies on. Most of these tests pin down when matching must
NOT happen.
"""

import textwrap

import pytest

from app import db, matching, skills
from app.facets import build_facet, normalize_status

SUBSCRIPTION = textwrap.dedent(
    """\
    ---
    name: sub
    description: A recurring subscription.
    applies_to: [text]
    extra_schema:
      service:
        type: string
        description: What is being paid for.
      cost:
        type: ["number", "null"]
        description: Recurring charge.
      state:
        type: ["string", "null"]
        description: active or cancelled.
    promote:
      vendor: service
      amount: cost
      status: state
    identity_fields: [service]
    ---
    Notes.
    """
)

RECEIPT = textwrap.dedent(
    """\
    ---
    name: purchase
    description: A one-off purchase.
    applies_to: [text]
    extra_schema:
      merchant:
        type: ["string", "null"]
        description: Who was paid.
    ---
    Each purchase is its own thing.
    """
)


@pytest.fixture
def test_skills(tmp_path, monkeypatch):
    from app import config

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "sub.md").write_text(SUBSCRIPTION, encoding="utf-8")
    (skills_dir / "purchase.md").write_text(RECEIPT, encoding="utf-8")
    monkeypatch.setattr(skills, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    return skills_dir


@pytest.fixture
def sub_skill(test_skills):
    return skills.get_skill("sub")


def make_record(skill, data, label=""):
    """Store a record the way a real capture would."""
    entry_id = db.insert_entry(
        source_type="text", title="note", raw_text="x", summary="",
        category="Finance", tags=[], skill=skill.id,
    )
    return db.insert_facet(entry_id=entry_id, **build_facet(skill, {**data, "label": label}))


def test_a_skill_without_identity_fields_is_never_updatable(test_skills):
    assert skills.get_skill("purchase").updatable is False
    assert skills.get_skill("sub").updatable is True


def test_shortlist_finds_the_same_service_by_loose_name(sub_skill):
    make_record(sub_skill, {"service": "Notion Plus", "cost": 10, "state": "active"})

    candidates = matching.shortlist(sub_skill, build_facet(sub_skill, {"label": "", "service": "notion", "cost": 12}))

    assert len(candidates) == 1


def test_shortlist_ignores_unrelated_services(sub_skill):
    make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    assert matching.shortlist(sub_skill, build_facet(sub_skill, {"label": "", "service": "Spotify", "cost": 5})) == []


def test_no_candidates_means_no_model_call(sub_skill, stub_llm):
    """Most captures never reach the matcher, which is what keeps it cheap."""
    incoming = build_facet(sub_skill, {"label": "", "service": "Spotify", "cost": 5})
    assert matching.find_match(sub_skill, incoming) is None
    assert stub_llm.calls == []


def test_only_a_confident_match_is_applied(sub_skill, stub_llm):
    facet_id = make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "cost": 12})

    stub_llm.returns({"match_id": facet_id, "confidence": "medium", "reason": "maybe"})
    assert matching.find_match(sub_skill, incoming) is None, "a medium-confidence guess must not merge"

    stub_llm.returns({"match_id": facet_id, "confidence": "high", "reason": "same service"})
    assert matching.find_match(sub_skill, incoming)["id"] == facet_id


def test_a_match_id_outside_the_candidates_is_ignored(sub_skill, stub_llm):
    make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    stub_llm.returns({"match_id": 9999, "confidence": "high", "reason": "hallucinated"})

    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "cost": 12})
    assert matching.find_match(sub_skill, incoming) is None


def test_a_provider_failure_creates_a_new_record(sub_skill, monkeypatch):
    """A duplicate is visible and deletable; a bad merge is neither."""
    from app import llm

    make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    monkeypatch.setattr(llm, "complete_json", lambda **kw: (_ for _ in ()).throw(llm.LLMError("down")))

    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "cost": 12})
    assert matching.find_match(sub_skill, incoming) is None


# --- applying an update -----------------------------------------------------


def test_an_update_changes_the_record_and_keeps_the_old_value(sub_skill):
    facet_id = make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"}, label="Notion $10")
    existing = db.get_facet(facet_id)
    incoming = build_facet(sub_skill, {"label": "Notion $12", "service": "Notion", "cost": 12, "state": "active"})

    updated = matching.apply_update(existing=existing, skill=sub_skill, incoming=incoming, entry_id=None)

    assert updated["amount"] == 12.0
    assert "amount" in updated["changed_fields"]

    revisions = db.list_facet_revisions(facet_id)
    assert revisions[0]["changes"]["cost"] == {"from": 10, "to": 12}


def test_an_empty_incoming_value_never_clears_a_field(sub_skill):
    """"I cancelled Notion" must not wipe the price just because that note
    didn't mention it."""
    facet_id = make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    existing = db.get_facet(facet_id)
    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "cost": None, "state": "cancelled"})

    updated = matching.apply_update(existing=existing, skill=sub_skill, incoming=incoming, entry_id=None)

    assert updated["amount"] == 10.0
    assert updated["data"]["cost"] == 10


def test_cancelling_closes_the_record(sub_skill):
    """Otherwise a cancelled subscription keeps showing on the agenda and in
    the monthly spend total."""
    facet_id = make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    existing = db.get_facet(facet_id)
    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "state": "cancelled"})

    updated = matching.apply_update(existing=existing, skill=sub_skill, incoming=incoming, entry_id=None)
    assert updated["status"] == "done"


def test_mentioning_a_record_with_nothing_new_still_records_the_mention(sub_skill):
    facet_id = make_record(sub_skill, {"service": "Notion", "cost": 10, "state": "active"})
    existing = db.get_facet(facet_id)
    incoming = build_facet(sub_skill, {"label": "", "service": "Notion", "cost": 10, "state": "active"})

    matching.apply_update(existing=existing, skill=sub_skill, incoming=incoming, entry_id=None)

    revisions = db.list_facet_revisions(facet_id)
    assert len(revisions) == 1
    assert revisions[0]["changes"] == {}


@pytest.mark.parametrize(
    "word,expected",
    [
        ("cancelled", "done"), ("canceled", "done"), ("rejected", "done"),
        ("withdrawn", "done"), ("expired", "done"), ("completed", "done"),
        ("active", "open"), ("paused", "open"), ("in progress", "open"),
        ("applied", "open"), ("gibberish", None), (None, None), (12, None),
    ],
)
def test_status_words_map_onto_the_facet_lifecycle(word, expected):
    assert normalize_status(word) == expected


def test_an_unrecognized_status_word_leaves_the_status_alone(sub_skill):
    """status is NOT NULL -- an unknown word must not blank it."""
    facet = build_facet(sub_skill, {"label": "", "service": "Notion", "state": "wibble"})
    assert "status" not in facet
