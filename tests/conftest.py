"""Shared fixtures.

Every test gets its own SQLite file so nothing touches data/lifelog.db and
tests can't leak state into each other. `db.DB_PATH` is a module-level name
read on each connection, so pointing it at a temp file is enough.
"""

import json
import types

import pytest

from app import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the app at a fresh database for the duration of one test."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    yield path


@pytest.fixture(autouse=True)
def no_provider_keys(monkeypatch):
    """Stop tests inheriting real keys from the developer's .env.

    Without this a failing stub could fall through to a live API call, which
    would be slow, cost money, and make results depend on the network.
    """
    for name in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "GOOGLE_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "DEEPSEEK_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def make_response(payload):
    """An Anthropic-style response carrying `payload` as JSON."""
    return types.SimpleNamespace(
        stop_reason="end_turn",
        content=[types.SimpleNamespace(type="text", text=json.dumps(payload))],
    )


@pytest.fixture
def stub_llm(monkeypatch):
    """Queue JSON payloads for successive llm.complete_json calls.

    Returns a recorder whose `.calls` holds the kwargs of each call, so tests
    can assert on the schema and prompt that were actually sent.
    """
    from app import llm

    class Recorder:
        def __init__(self):
            self.queue = []
            self.calls = []

        def returns(self, *payloads):
            self.queue.extend(payloads)
            return self

        def _complete(self, **kwargs):
            self.calls.append(kwargs)
            if not self.queue:
                raise AssertionError("llm.complete_json called more times than stubbed")
            return self.queue.pop(0)

    recorder = Recorder()
    monkeypatch.setattr(llm, "complete_json", recorder._complete)
    # organize/search/selfmod import the module, so patching the attribute
    # covers them all.
    return recorder


@pytest.fixture
def fake_http(monkeypatch):
    """Intercept the OpenAI-compatible transport and capture the request."""
    import httpx

    from app import llm

    state = {"captured": {}, "payload": {}, "status": 200}

    class FakeResponse:
        def __init__(self):
            self.status_code = state["status"]
            self.text = json.dumps(state["payload"])

        def json(self):
            return state["payload"]

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            state["captured"] = {"url": url, "headers": headers, "body": json}
            return FakeResponse()

    monkeypatch.setattr(
        llm, "httpx", types.SimpleNamespace(Client=FakeClient, HTTPError=httpx.HTTPError)
    )
    return state
