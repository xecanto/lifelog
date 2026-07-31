"""HTTP surface: status codes, payload shapes, and error messages."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

TODAY = date.today()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seeded():
    entry_id = db.insert_entry(
        source_type="voice", title="Notion Plus subscription", raw_text="...",
        summary="Notion at $10/month.", category="Finance", tags=["notion"],
        skill="subscription", metadata={"skills": ["subscription", "reminder"]},
    )
    sub_id = db.insert_facet(
        entry_id=entry_id, kind="subscription", label="Notion Plus - $10/mo",
        data={"service": "Notion Plus"}, due_at=(TODAY + timedelta(days=12)).isoformat(),
        cadence="monthly", amount=10.0, currency="USD", vendor="Notion",
    )
    db.insert_facet(
        entry_id=entry_id, kind="reminder", label="Renews soon", due_at=TODAY.isoformat(),
        data={"remind_about": "Cancel if unused"},
    )
    return {"entry_id": entry_id, "sub_id": sub_id}


def test_health(client):
    assert client.get("/").json()["status"] == "ok"


def test_entries_carry_their_facets(client, seeded):
    entry = client.get(f"/api/entries/{seeded['entry_id']}").json()
    assert {f["kind"] for f in entry["facets"]} == {"subscription", "reminder"}

    listed = client.get("/api/entries").json()
    assert len(listed["entries"][0]["facets"]) == 2


def test_agenda_groups_by_day(client, seeded):
    agenda = client.get("/api/agenda?days=30").json()
    assert agenda["counts"] == {"overdue": 0, "due_today": 1, "upcoming": 1}
    assert agenda["due_today"][0]["entry_title"] == "Notion Plus subscription"


def test_agenda_rejects_a_nonsense_window(client):
    response = client.get("/api/agenda?days=-5")
    assert response.status_code == 400


def test_facets_report_recurring_spend(client, seeded):
    body = client.get("/api/facets?kind=subscription").json()
    assert body["spend"]["monthly_by_currency"] == {"USD": 10.0}


def test_acting_on_a_facet_removes_it_from_the_agenda(client, seeded):
    response = client.patch(f"/api/facets/{seeded['sub_id']}", json={"status": "done"})
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert client.get("/api/agenda?days=30").json()["counts"]["upcoming"] == 0
    # The action is recorded for reflection to learn from.
    assert any(e["kind"] == "facet_action" for e in db.list_events())


@pytest.mark.parametrize(
    "method,path,payload,status",
    [
        ("patch", "/api/facets/9999", {"status": "done"}, 404),
        ("get", "/api/entries/9999", None, 404),
        ("get", "/api/modifications/9999", None, 404),
        ("post", "/api/modifications/9999/run", None, 404),
    ],
)
def test_missing_resources_are_404(client, method, path, payload, status):
    call = getattr(client, method)
    response = call(path, json=payload) if payload else call(path)
    assert response.status_code == status


def test_invalid_facet_status_is_rejected(client, seeded):
    response = client.patch(f"/api/facets/{seeded['sub_id']}", json={"status": "banana"})
    assert response.status_code == 400
    assert "Expected one of" in response.json()["detail"]


def test_deleting_an_entry_removes_its_facets(client, seeded):
    client.delete(f"/api/entries/{seeded['entry_id']}")
    assert client.get("/api/facets").json()["facets"] == []


# --- settings and self-modification ----------------------------------------


def test_settings_expose_defaults_and_choices(client):
    settings = {s["key"]: s for s in client.get("/api/settings").json()["settings"]}
    assert settings["self_modification_enabled"]["value"] is False
    assert "anthropic" in settings["llm_provider"]["choices"]


def test_providers_never_return_key_values(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    body = client.get("/api/providers").json()
    assert "super-secret" not in str(body)
    assert any(p["id"] == "openai" and p["has_key"] for p in body["providers"])


@pytest.mark.parametrize(
    "values,fragment",
    [
        ({"not_a_setting": 1}, "Unknown setting"),
        ({"agent_timeout_seconds": "soon"}, "expects a number"),
        ({"llm_provider": "skynet"}, "must be one of"),
    ],
)
def test_bad_settings_are_rejected(client, values, fragment):
    response = client.patch("/api/settings", json={"values": values})
    assert response.status_code == 400
    assert fragment in response.json()["detail"]


def test_a_request_is_pending_while_self_modification_is_off(client):
    job = client.post(
        "/api/modifications", json={"prompt": "Track my car servicing", "title": "Car", "kind": "skill"}
    ).json()
    assert job["status"] == "pending"
    assert job["prompt"] == "Track my car servicing"


def test_a_pending_job_can_be_cancelled_once(client):
    job = client.post("/api/modifications", json={"prompt": "x", "kind": "skill"}).json()

    assert client.post(f"/api/modifications/{job['id']}/cancel").json()["status"] == "cancelled"

    repeat = client.post(f"/api/modifications/{job['id']}/cancel")
    assert repeat.status_code == 400
    assert client.post(f"/api/modifications/{job['id']}/run").status_code == 400


@pytest.mark.parametrize(
    "payload,fragment",
    [({"prompt": "   ", "kind": "code"}, "needs a prompt"), ({"prompt": "x", "kind": "sudo"}, "Invalid kind")],
)
def test_bad_modification_requests_are_rejected(client, payload, fragment):
    response = client.post("/api/modifications", json=payload)
    assert response.status_code == 400
    assert fragment in response.json()["detail"]


def test_reflection_declines_when_there_is_too_little_to_learn_from(client, seeded):
    body = client.post("/api/reflect").json()
    assert body["ran"] is False
    assert "at least" in body["reason"]
    assert body["proposals"] == []
