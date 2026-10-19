"""Provider selection: what is chosen, what is refused, what never leaks.

No network. Every HTTP call is faked, because what matters here is not that
an OpenAI-compatible endpoint works - it does - but that Kavach picks the
right one, records which one answered, and keeps the key out of everything
it writes down.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace
from io import BytesIO
from typing import Any
from unittest.mock import patch

import pytest

from kavach.llm import providers
from kavach.llm.client import LlmClient, LlmError, OllamaClient

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
SECRET = "sk-test-do-not-leak-123456"


def a_reply(content: str = '{"answer": "ok"}', model: str = "some-model") -> Any:
    return BytesIO(json.dumps({
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }).encode())


class FakeUrlopen:
    """Records the request it was given and returns a canned reply."""

    def __init__(self, reply: Any = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.request: Any = None

    def __call__(self, req: Any, timeout: float = 0) -> Any:
        self.request = req
        if self.error is not None:
            raise self.error
        body = self.reply if self.reply is not None else a_reply()

        class Ctx:
            def __enter__(self) -> Any:
                return body

            def __exit__(self, *a: Any) -> None:
                return None

        return Ctx()


@pytest.fixture
def no_settings_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keys come from the test, never from the developer's real .env."""
    monkeypatch.setattr(providers, "key_for", lambda spec: "")


# --- selection -------------------------------------------------------------


def test_ollama_is_the_default_and_needs_no_key() -> None:
    """PL-02: no cloud key may be required for Kavach to run."""
    client = providers.build()
    assert isinstance(client, OllamaClient)
    assert isinstance(client, LlmClient)


def test_every_listed_provider_can_actually_be_built(
    no_settings_key: None,
) -> None:
    for name in providers.names():
        client = providers.build(name, model="explicit-model",
                                 api_key="x" if name != "ollama" else "")
        assert isinstance(client, LlmClient), name
        assert client.model, f"{name} resolved to no model"


def test_a_provider_with_no_confirmed_default_model_demands_one(
    no_settings_key: None,
) -> None:
    """A row with no default must refuse, rather than guess a model name.

    This asserted `opencodezen.default_model == ""` until 2026-10-19, when
    its model list was read from a live `GET /zen/v1/models` (85 models,
    public, no key) and the row got a real default. The fact changed for a
    checked reason; the guarantee it was protecting has not, so it is tested
    here on the mechanism instead of on one provider's data - which is what
    it should have been doing in the first place.
    """
    blank = replace(providers.PROVIDERS["opencodezen"], default_model="")
    with (
        patch.dict(providers.PROVIDERS, {"opencodezen": blank}),
        pytest.raises(LlmError, match="no default model"),
    ):
        providers.build("opencodezen", api_key="x")


def test_no_provider_ships_a_default_model_nobody_looked_up(
    no_settings_key: None,
) -> None:
    """Every default in the table is a string someone read off that
    provider's own model list, and the note says where. An invented model
    name fails at the first request with an error about the model, which
    reads like the provider is broken - see the `opencodezen` row, which was
    nearly deleted on exactly that misreading."""
    for name, spec in providers.PROVIDERS.items():
        assert spec.note, (
            f"{name} ships without a note saying where its endpoint and "
            f"default model came from")


def test_an_unknown_provider_is_refused_with_the_list(
    no_settings_key: None,
) -> None:
    with pytest.raises(LlmError, match="unknown provider"):
        providers.build("not-a-provider")


def test_the_provider_is_never_inferred_from_which_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A measurement whose model depends on the contents of a .env file
    nobody re-reads is not a measurement. Selection is explicit, always."""
    monkeypatch.setattr(providers, "key_for", lambda spec: SECRET)
    assert isinstance(providers.build(), OllamaClient)


def test_no_base_url_in_the_table_includes_the_endpoint_path() -> None:
    """Including `/chat/completions` in a base URL doubles the path, and the
    404 that follows reads like an auth failure. Caught here instead."""
    for name, spec in providers.PROVIDERS.items():
        assert not spec.base_url.rstrip("/").endswith("chat/completions"), name
        assert spec.base_url.startswith("https://"), name


def test_tokenrouter_is_absent_rather_than_guessed() -> None:
    """It was asked for and could not be confirmed to exist. A row with an
    invented base URL fails at the first call with a misleading error, which
    is worse than not offering it."""
    assert "tokenrouter" not in providers.PROVIDERS


# --- the key ---------------------------------------------------------------


def test_a_missing_key_names_the_variable_to_set(no_settings_key: None) -> None:
    client = providers.build("groq", model="m")
    with pytest.raises(LlmError, match="KAVACH_GROQ_API_KEY"):
        client.structured("s", "u", SCHEMA)


def test_a_missing_key_is_not_an_error_until_the_provider_is_used(
    no_settings_key: None,
) -> None:
    """Blank is a supported state. Building the client must not raise, or a
    console that lists providers cannot list the ones you have not paid for."""
    client = providers.build("openrouter", model="m")
    assert client.available() is False


def test_the_key_is_sent_as_a_bearer_token_and_not_in_the_url(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    providers.build("groq", model="m", api_key=SECRET).structured(
        "s", "u", SCHEMA)

    assert fake.request.headers["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in fake.request.full_url


def test_a_provider_that_echoes_the_key_back_does_not_leak_it(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE test this module exists for. The audit log is append-only, so a
    key that reaches an error message reaches it permanently."""
    err = urllib.error.HTTPError(
        "https://api.groq.com/openai/v1/chat/completions", 401, "Unauthorized",
        {},  # type: ignore[arg-type]
        BytesIO(f'{{"error":"bad key {SECRET}"}}'.encode()),
    )
    monkeypatch.setattr(urllib.request, "urlopen",
                        FakeUrlopen(error=err))
    client = providers.build("groq", model="m", api_key=SECRET)

    with pytest.raises(LlmError) as caught:
        client.structured("s", "u", SCHEMA)
    assert SECRET not in str(caught.value)
    assert "***" in str(caught.value)
    assert "401" in str(caught.value)


# --- the request we actually send ------------------------------------------


def test_structured_output_is_requested_strictly(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cloud equivalent of Ollama's grammar constraint. Without `strict`
    the schema is a suggestion, and `rca/schema.py` records what an
    unconstrained decoder costs this project."""
    fake = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    providers.build("openrouter", model="m", api_key=SECRET).structured(
        "s", "u", SCHEMA)

    sent = json.loads(fake.request.data)
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"] == SCHEMA
    assert sent["temperature"] == 0.0


def test_the_endpoint_is_the_base_url_plus_chat_completions(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    providers.build("gemini", model="m", api_key=SECRET).structured(
        "s", "u", SCHEMA)
    assert fake.request.full_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai"
        "/chat/completions"
    )


# --- provenance ------------------------------------------------------------


def test_the_response_records_which_provider_answered(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every figure in this project is "model X scored Y". Provenance travels
    with the response so a caller cannot forget to record it."""
    monkeypatch.setattr(urllib.request, "urlopen",
                        FakeUrlopen(a_reply(model="llama-3.3-70b-versatile")))
    reply = providers.build("groq", api_key=SECRET).structured(
        "s", "u", SCHEMA)

    assert reply.provider == "groq"
    assert reply.model == "llama-3.3-70b-versatile"
    assert reply.prompt_tokens == 11
    assert reply.completion_tokens == 22
    assert reply.parsed() == {"answer": "ok"}


def test_an_ollama_response_says_ollama() -> None:
    from kavach.llm.client import LlmResponse

    assert LlmResponse(raw="{}", model="llama3.2", latency_s=0.1).provider == (
        "ollama"
    )


# --- failure modes ---------------------------------------------------------


def test_a_null_content_is_an_error_not_an_empty_diagnosis(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal or a length cut-off arrives as `content: null`. Letting that
    become an empty string would hand the validator something that parses."""
    body = BytesIO(json.dumps(
        {"model": "m", "choices": [{"message": {"content": None}}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(body))

    with pytest.raises(LlmError, match="no content"):
        providers.build("groq", model="m", api_key=SECRET).structured(
            "s", "u", SCHEMA)


def test_an_unexpected_shape_is_an_error_not_a_crash(
    no_settings_key: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = BytesIO(json.dumps({"something": "else"}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(body))

    with pytest.raises(LlmError, match="unexpected"):
        providers.build("groq", model="m", api_key=SECRET).structured(
            "s", "u", SCHEMA)


def test_a_proxied_base_url_is_refused_for_cloud_providers_too(
    no_settings_key: None,
) -> None:
    """PRD §6.3: Kavach's own model must never go through the fault-injection
    proxy, or injecting F01 would blind the diagnostician. A cloud URL cannot
    normally be proxied, but the check is free and the rule has no exception."""
    with pytest.raises(LlmError, match="fault-injection proxy"):
        providers.build("groq", model="m",
                        base_url="http://toxiproxy:21434/v1", api_key="k")
