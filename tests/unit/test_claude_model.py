"""ClaudeModel against a fake SDK client: no network, no key."""

import logging
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from pydantic import BaseModel, ValidationError

from groundwork.adapters.model.claude import FALLBACK_BETA, ClaudeModel
from groundwork.adapters.model.recording import DEFAULT_SPECS
from groundwork.core.domain.errors import ModelError, ModelRefusalError
from groundwork.core.ports.model import Quote

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
DOC = "We keep emails short. We never put a discount in writing."


class Label(BaseModel):
    label: str


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_creation_input_tokens=50,
        cache_read_input_tokens=0,
    )


def _message(content: list[Any] = (), stop: str = "end_turn", **extra: Any) -> SimpleNamespace:  # type: ignore[assignment]
    return SimpleNamespace(
        content=list(content), stop_reason=stop, usage=_usage(), model="claude-sonnet-5-5", **extra
    )


def _text(text: str, citations: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text, citations=citations)


def _cited(text: str) -> SimpleNamespace:
    start = DOC.index(text)
    return SimpleNamespace(
        type="char_location",
        cited_text=text,
        start_char_index=start,
        end_char_index=start + len(text),
    )


class FakeMessages:
    def __init__(self, parse: list[Any] | None = None, create: Any = None) -> None:
        self._parse = list(parse or [])
        self._create = create
        self.calls: list[dict[str, Any]] = []

    def parse(self, **params: Any) -> Any:
        self.calls.append(params)
        result = self._parse.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def create(self, **params: Any) -> Any:
        self.calls.append(params)
        return self._create


def _model(messages: FakeMessages) -> ClaudeModel:
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeModel(client, DEFAULT_SPECS)


def _validation_error() -> ValidationError:
    try:
        Label.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError


def test_structured_output_uses_output_format_not_forced_tools() -> None:
    messages = FakeMessages(parse=[_message(parsed_output=Label(label="ok"))])
    answer = _model(messages).complete_structured(
        tier="cheap", system="s", user="u", schema=Label, document=DOC
    )
    assert answer.value == Label(label="ok")
    params = messages.calls[0]
    assert params["output_format"] is Label
    assert "tool_choice" not in params and "tools" not in params
    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"] == {"effort": "low"}


def test_structured_output_retries_once_then_fails() -> None:
    ok = FakeMessages(parse=[_validation_error(), _message(parsed_output=Label(label="ok"))])
    assert _model(ok).complete_structured(tier="cheap", system="s", user="u", schema=Label)
    bad = FakeMessages(parse=[_validation_error(), _validation_error()])
    with pytest.raises(ModelError, match="did not match Label"):
        _model(bad).complete_structured(tier="cheap", system="s", user="u", schema=Label)


def test_document_is_a_cached_data_block_before_the_instruction() -> None:
    messages = FakeMessages(parse=[_message(parsed_output=Label(label="ok"))])
    _model(messages).complete_structured(
        tier="cheap", system="s", user="u", schema=Label, document=DOC
    )
    document, instruction = messages.calls[0]["messages"][0]["content"]
    assert document["type"] == "document"
    assert document["source"] == {"type": "text", "media_type": "text/plain", "data": DOC}
    assert document["cache_control"] == {"type": "ephemeral"}
    assert document["citations"] == {"enabled": False}
    assert instruction == {"type": "text", "text": "u"}


def test_cite_maps_citations_to_verbatim_quotes() -> None:
    content = [
        _text("- "),
        _text("Keep emails short.", [_cited("We keep emails short.")]),
        _text("\n- "),
        _text("No discount in writing.", [_cited("We never put a discount in writing.")]),
        _text("\n- An uncited idea"),
    ]
    messages = FakeMessages(create=_message(content))
    answer = _model(messages).cite(tier="extraction", system="s", instruction="i", document=DOC)

    first, second, third = answer.value
    assert first.text == "Keep emails short."
    assert first.quotes == (Quote(text="We keep emails short.", start=0, end=21),)
    assert all(DOC[q.start : q.end] == q.text for q in second.quotes)
    assert third.quotes == ()
    assert messages.calls[0]["messages"][0]["content"][0]["citations"] == {"enabled": True}


def test_extraction_tier_opts_into_the_server_side_fallback() -> None:
    messages = FakeMessages(create=_message([_text("- a")]))
    answer = _model(messages).cite(tier="extraction", system="s", instruction="i", document=DOC)
    assert messages.calls[0]["fallbacks"] == "default"
    assert messages.calls[0]["betas"] == [FALLBACK_BETA]
    assert answer.model == "claude-sonnet-5-5"
    cheap = FakeMessages(create=_message([_text("hi")]))
    _model(cheap).complete_text(tier="cheap", system="s", user="u")
    assert "fallbacks" not in cheap.calls[0]


def test_usage_includes_cached_input() -> None:
    messages = FakeMessages(create=_message([_text("hi")]))
    answer = _model(messages).complete_text(tier="cheap", system="s", user="u")
    assert answer.value == "hi"
    assert (answer.usage.input_tokens, answer.usage.output_tokens) == (150, 20)


def test_refusal_and_truncation_raise() -> None:
    refusal = _message(stop="refusal", stop_details=SimpleNamespace(category="cyber"))
    with pytest.raises(ModelRefusalError, match="cyber"):
        _model(FakeMessages(create=refusal)).complete_text(tier="cheap", system="s", user="u")
    with pytest.raises(ModelError, match="truncated"):
        _model(FakeMessages(create=_message(stop="max_tokens"))).complete_text(
            tier="cheap", system="s", user="u"
        )


def test_missing_parsed_output_raises() -> None:
    messages = FakeMessages(parse=[_message(parsed_output=None)])
    with pytest.raises(ModelError, match="no Label"):
        _model(messages).complete_structured(tier="cheap", system="s", user="u", schema=Label)


def test_nothing_is_logged(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    caplog.set_level(logging.DEBUG)
    messages = FakeMessages(create=_message([_text("hi")]))
    _model(messages).complete_text(tier="cheap", system="s", user="u")
    assert "sk-ant" not in caplog.text
    assert all("key" not in name for name in messages.calls[0])


@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (anthropic.APIConnectionError(request=REQUEST), "Connection error"),
        (
            anthropic.AuthenticationError(
                "invalid x-api-key", response=httpx.Response(401, request=REQUEST), body=None
            ),
            "invalid x-api-key",
        ),
    ],
)
def test_api_failures_become_model_errors_naming_the_cause(error: Exception, shown: str) -> None:
    model = _model(FakeMessages(parse=[error]))
    with pytest.raises(ModelError, match=shown):
        model.complete_structured(tier="cheap", system="s", user="u", schema=Label)
