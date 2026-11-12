import pytest
from pydantic import ValidationError

from groundwork.core.domain.errors import AgentError, AgentLimitError, GroundworkError
from groundwork.core.domain.harmonize import ApprovalItem, Decision, HarmonizedEmail


def _item(**fields: object) -> ApprovalItem:
    data = {
        "id": "case-1",
        "contact_id": "acme-c-1",
        "recipient": "ana.silva@example.com",
        "email": HarmonizedEmail(subject="s", body="b", rationale="r"),
        "decision": Decision(route="approval", reasons=("external",)),
        **fields,
    }
    return ApprovalItem.model_validate(data)


def test_an_item_starts_pending_with_no_reason() -> None:
    item = _item()
    assert (item.status, item.reason) == ("pending", None)


def test_an_item_is_frozen_and_the_status_is_one_of_three() -> None:
    with pytest.raises(ValidationError):
        _item().status = "approved"
    with pytest.raises(ValidationError):
        _item(status="sent")


def test_a_limit_error_names_the_limit_and_is_an_agent_error() -> None:
    error = AgentLimitError("steps", "9 tool calls, limit 8")
    assert isinstance(error, AgentError) and isinstance(error, GroundworkError)
    assert error.limit == "steps"
    assert "steps limit exceeded (9 tool calls, limit 8)" in str(error)
