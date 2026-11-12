import pytest
from pydantic import ValidationError

from groundwork.core.domain.harmonize import (
    AgentResult,
    Decision,
    HarmonizedEmail,
    HarmonizeRequest,
    request_hash,
)


def _request(**fields: object) -> HarmonizeRequest:
    data = {
        "contact_id": "acme-c-1",
        "channel": "external",
        "draft": "Hi, Pro costs 1490 EUR.",
        **fields,
    }
    return HarmonizeRequest.model_validate(data)


def test_the_case_id_is_the_given_one() -> None:
    assert _request(case_id="demo-external-ok").id == "demo-external-ok"


def test_the_case_id_defaults_to_twelve_hex_characters_of_the_request_hash() -> None:
    request = _request()
    assert request.id == request_hash(request)[:12]
    assert len(request.id) == 12 and int(request.id, 16) >= 0


def test_the_hash_depends_on_the_request_and_not_on_the_case_id() -> None:
    assert request_hash(_request()) == request_hash(_request(case_id="x"))
    assert request_hash(_request()) != request_hash(_request(draft="Another draft."))
    assert request_hash(_request()) != request_hash(_request(channel="internal"))
    assert request_hash(_request()) != request_hash(_request(contact_id="acme-c-2"))


@pytest.mark.parametrize("bad", ["", "has space", "../escape", "-lead"])
def test_a_case_id_cannot_walk_out_of_the_traces_directory(bad: str) -> None:
    with pytest.raises(ValidationError):
        _request(case_id=bad)


def test_the_channel_is_internal_or_external() -> None:
    with pytest.raises(ValidationError):
        _request(channel="any")


def test_a_decision_always_has_a_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        Decision(route="blocked", reasons=())
    assert Decision(route="approval", reasons=("external email",)).route == "approval"


def test_the_route_is_one_of_three() -> None:
    with pytest.raises(ValidationError):
        Decision(route="send", reasons=("x",))  # type: ignore[arg-type]


def test_an_agent_result_defaults_to_no_steps_and_no_cost() -> None:
    result = AgentResult(email=HarmonizedEmail(subject="s", body="b", rationale="r"))
    assert result.steps == () and result.usage.input_tokens == 0
    assert result.email.cited_nodes == ()
