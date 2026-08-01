"""Provider abstraction: request shaping, structured-output tiers, errors."""

import pytest

from app import llm, settings

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def content(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


@pytest.fixture
def openai_ready(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    settings.set_many({"llm_provider": "openai", "llm_model": "", "llm_base_url": ""})
    return fake_http


@pytest.fixture
def deepseek_ready(monkeypatch, fake_http):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    settings.set_many({"llm_provider": "deepseek", "llm_model": "", "llm_base_url": ""})
    return fake_http


@pytest.mark.parametrize("provider_id", [p.id for p in llm.PROVIDERS])
def test_every_provider_is_selectable(provider_id):
    settings.set_many({"llm_provider": provider_id})
    assert llm.active_provider().id == provider_id


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        settings.set_many({"llm_provider": "skynet"})


def test_blank_model_falls_back_to_the_provider_default():
    settings.set_many({"llm_provider": "openai", "llm_model": ""})
    assert llm.active_model() == "gpt-4o"
    settings.set_many({"llm_model": "gpt-4o-mini"})
    assert llm.active_model() == "gpt-4o-mini"


def test_api_keys_are_never_exposed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    described = llm.describe_providers()
    assert "super-secret" not in repr(described)
    assert any(p["id"] == "openai" and p["has_key"] for p in described)


def test_schema_is_enforced_server_side_where_supported(openai_ready):
    openai_ready["payload"] = content('{"answer": "hi"}')
    result = llm.complete_json(system="sys", user_content="hello", schema=SCHEMA, schema_name="answer")

    assert result == {"answer": "hi"}
    body = openai_ready["captured"]["body"]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    # No need to duplicate the schema into the prompt when it's enforced.
    assert "JSON schema" not in body["messages"][0]["content"]
    assert openai_ready["captured"]["url"] == "https://api.openai.com/v1/chat/completions"
    assert openai_ready["captured"]["headers"]["Authorization"] == "Bearer test-openai"


def test_weaker_providers_get_the_schema_in_the_prompt(deepseek_ready):
    deepseek_ready["payload"] = content('{"answer": "hi"}')
    assert llm.complete_json(system="sys", user_content="hello", schema=SCHEMA) == {"answer": "hi"}

    body = deepseek_ready["captured"]["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON schema" in body["messages"][0]["content"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"answer": "plain"}', {"answer": "plain"}),
        ('```json\n{"answer": "fenced"}\n```', {"answer": "fenced"}),
        ('Sure!\n{"answer": "prefixed"}\nHope that helps.', {"answer": "prefixed"}),
    ],
)
def test_lenient_parsing_for_providers_that_dont_guarantee_shape(deepseek_ready, raw, expected):
    deepseek_ready["payload"] = content(raw)
    assert llm.complete_json(system="s", user_content="u", schema=SCHEMA) == expected


@pytest.mark.parametrize("raw", ["not json at all", "[1,2,3]", ""])
def test_unusable_responses_raise(deepseek_ready, raw):
    deepseek_ready["payload"] = content(raw)
    with pytest.raises(llm.LLMError):
        llm.complete_json(system="s", user_content="u", schema=SCHEMA)


def test_a_refusal_is_none_not_an_error(deepseek_ready):
    deepseek_ready["payload"] = {"choices": [{"message": {"refusal": "no", "content": None}}]}
    assert llm.complete_json(system="s", user_content="u", schema=SCHEMA) is None


def test_provider_error_message_is_surfaced(deepseek_ready):
    deepseek_ready["payload"] = {"error": {"message": "Incorrect API key provided"}}
    deepseek_ready["status"] = 401
    with pytest.raises(llm.LLMError, match="Incorrect API key"):
        llm.complete_json(system="s", user_content="u", schema=SCHEMA)


def test_list_shaped_error_body_still_reports_the_real_message(deepseek_ready):
    """Google returns a LIST of error objects; .get() on that used to raise
    inside the error handler and hide the real failure."""
    deepseek_ready["payload"] = [{"error": {"code": 429, "message": "You exceeded your current quota"}}]
    deepseek_ready["status"] = 429
    with pytest.raises(llm.LLMError, match="exceeded your current quota"):
        llm.complete_json(system="s", user_content="u", schema=SCHEMA)


def test_missing_key_says_which_variable_to_set():
    settings.set_many({"llm_provider": "deepseek"})
    with pytest.raises(Exception, match="DEEPSEEK_API_KEY"):
        llm.complete_json(system="s", user_content="u", schema=SCHEMA)


def test_vision_uses_the_openai_image_block(openai_ready):
    openai_ready["payload"] = content("A photo of a receipt.")
    assert llm.describe_image(prompt="describe", media_type="image/png", b64_data="QUJD") == "A photo of a receipt."

    block = openai_ready["captured"]["body"]["messages"][0]["content"][0]
    assert block["image_url"]["url"] == "data:image/png;base64,QUJD"


def test_anthropic_vision_path_builds_a_native_image_block(monkeypatch):
    """The Anthropic transport uses a different content shape from the
    OpenAI-compatible one, and only the latter was covered -- which let a
    stale client call sit in this path unnoticed."""
    import types

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    settings.set_many({"llm_provider": "anthropic", "llm_model": "", "llm_base_url": ""})

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            stop_reason="end_turn",
            content=[types.SimpleNamespace(type="text", text="A receipt.")],
        )

    monkeypatch.setattr(
        llm,
        "_anthropic_client",
        lambda key, base_url: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=fake_create)
        ),
    )

    assert llm.describe_image(prompt="describe", media_type="image/png", b64_data="QUJD") == "A receipt."

    block = captured["messages"][0]["content"][0]
    assert block["type"] == "image"
    assert block["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}


def test_provider_without_vision_refuses_clearly(deepseek_ready):
    with pytest.raises(llm.LLMError, match="can't process images"):
        llm.describe_image(prompt="d", media_type="image/png", b64_data="QUJD")


def test_base_url_override_redirects_requests(openai_ready):
    settings.set_many({"llm_base_url": "https://gw.example.ai/v1/"})
    openai_ready["payload"] = content('{"answer": "x"}')
    llm.complete_json(system="s", user_content="u", schema=SCHEMA)
    assert openai_ready["captured"]["url"] == "https://gw.example.ai/v1/chat/completions"


def test_base_url_is_scoped_per_provider():
    """One global override would send OpenAI requests to an Anthropic gateway."""
    settings.set_many({"llm_provider": "anthropic", "llm_base_url": "https://gw.apito.ai"})
    assert llm.active_base_url() == "https://gw.apito.ai"

    settings.set_many({"llm_provider": "openai", "llm_model": ""})
    assert llm.active_base_url() == "https://api.openai.com/v1"

    settings.set_many({"llm_provider": "anthropic"})
    assert llm.active_base_url() == "https://gw.apito.ai"
