"""Follow-up questions: which get asked, and how answers fold back in.

Nothing here names a real field like "cost" outside a fixture skill -- the
whole point is that the backend learns what to ask from the skill file.
"""

import textwrap

import pytest

from app import db, skills
from app.clarify import apply_answers, pending_questions, questions_for_facet, with_questions

SKILL = textwrap.dedent(
    """\
    ---
    name: gadget
    description: A gadget the user owns.
    applies_to: [text]
    extra_schema:
      brand:
        type: ["string", "null"]
        description: Who makes it.
      price:
        type: ["number", "null"]
        description: What it cost, as a plain number.
      currency:
        type: ["string", "null"]
        description: Currency code.
      warranty_until:
        type: ["string", "null"]
        description: ISO date the warranty ends.
    promote:
      amount: price
      currency: currency
      due_at: warranty_until
      vendor: brand
    ask_if_missing:
      price: How much did it cost?
      warranty_until: When does the warranty run out?
    ---
    Notes.
    """
)


@pytest.fixture
def gadget_skill(tmp_path, monkeypatch):
    from app import config

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "gadget.md").write_text(SKILL, encoding="utf-8")
    monkeypatch.setattr(skills, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    return skills.get_skill("gadget")


@pytest.fixture
def gadget_facet(gadget_skill):
    entry_id = db.insert_entry(
        source_type="text", title="New headphones", raw_text="Bought some Sony headphones",
        summary="", category="Personal", tags=[], skill="gadget",
    )
    facet_id = db.insert_facet(
        entry_id=entry_id, kind="gadget", label="Sony headphones",
        data={"brand": "Sony", "price": None, "currency": None, "warranty_until": None},
        vendor="Sony",
    )
    return db.get_facet(facet_id)


def test_only_declared_and_empty_fields_are_asked(gadget_facet):
    asked = {q["field"] for q in questions_for_facet(gadget_facet)}
    # price and warranty_until are declared in ask_if_missing and empty.
    # brand is filled; currency is empty but never declared.
    assert asked == {"price", "warranty_until"}


def test_the_declared_wording_is_used(gadget_facet):
    questions = {q["field"]: q["question"] for q in questions_for_facet(gadget_facet)}
    assert questions["price"] == "How much did it cost?"


def test_a_skill_that_asks_nothing_produces_no_questions():
    entry_id = db.insert_entry(
        source_type="text", title="t", raw_text="x", summary="", category="c", tags=[], skill="general",
    )
    facet_id = db.insert_facet(entry_id=entry_id, kind="recipe", data={"ingredients": []})
    assert questions_for_facet(db.get_facet(facet_id)) == []


def test_questions_are_gathered_across_an_entrys_facets(gadget_facet):
    entry = with_questions(db.get_entry(gadget_facet["entry_id"]))
    assert len(entry["pending_questions"]) == 2
    assert all(q["facet_id"] == gadget_facet["id"] for q in entry["pending_questions"])


def test_answers_are_normalized_and_promoted(gadget_facet, stub_llm):
    stub_llm.returns({"price": 199, "currency": "USD", "warranty_until": "2028-03-01"})

    updated = apply_answers(
        facet_id=gadget_facet["id"],
        answers={"price": "199 dollars", "warranty_until": "first of March 2028"},
    )

    # Promoted columns are recomputed, not just the data blob.
    assert updated["amount"] == 199.0
    assert updated["currency"] == "USD"
    assert updated["due_at"] == "2028-03-01"
    assert updated["data"]["price"] == 199


def test_a_reply_can_fill_an_adjacent_empty_field(gadget_facet, stub_llm):
    """"199 dollars" answers the price and names the currency, even though
    only the price was asked."""
    stub_llm.returns({"price": 199, "currency": "USD", "warranty_until": None})

    apply_answers(facet_id=gadget_facet["id"], answers={"price": "199 dollars"})

    offered = set(stub_llm.calls[0]["schema"]["properties"])
    assert "currency" in offered  # empty, so offered
    assert "brand" not in offered  # already filled, so protected


def test_an_answer_cannot_overwrite_a_field_that_already_has_a_value(gadget_facet, stub_llm):
    stub_llm.returns({"price": 199, "currency": None, "warranty_until": None})
    updated = apply_answers(facet_id=gadget_facet["id"], answers={"price": "199"})
    assert updated["data"]["brand"] == "Sony"


def test_answering_removes_the_question(gadget_facet, stub_llm):
    stub_llm.returns({"price": 199, "currency": "USD", "warranty_until": None})
    apply_answers(facet_id=gadget_facet["id"], answers={"price": "199 dollars"})

    remaining = pending_questions(db.get_entry(gadget_facet["entry_id"]))
    assert {q["field"] for q in remaining} == {"warranty_until"}


def test_an_unanswerable_reply_leaves_the_field_open(gadget_facet, stub_llm):
    """"I don't know" is a legitimate reply, not an error. Nothing is
    recorded, so the field stays empty and gets asked again."""
    stub_llm.returns({"price": None, "currency": None, "warranty_until": None})

    result = apply_answers(facet_id=gadget_facet["id"], answers={"price": "no idea"})

    assert result["recorded_fields"] == []
    assert result["amount"] is None
    still_asked = {q["field"] for q in pending_questions(db.get_entry(gadget_facet["entry_id"]))}
    assert "price" in still_asked


def test_blank_and_unknown_answers_are_rejected(gadget_facet):
    with pytest.raises(ValueError, match="No answers"):
        apply_answers(facet_id=gadget_facet["id"], answers={"price": "   "})
    with pytest.raises(ValueError, match="No answers"):
        apply_answers(facet_id=gadget_facet["id"], answers={"not_a_field": "x"})


def test_a_missing_facet_is_reported(gadget_skill):
    with pytest.raises(ValueError, match="not found"):
        apply_answers(facet_id=9999, answers={"price": "10"})
