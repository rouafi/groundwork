"""ApprovalPort contract: one suite, every adapter.

Written against the port only. To cover a new adapter, add a factory to `ADAPTERS`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from groundwork.adapters.approval.file import FileApproval
from groundwork.core.domain.errors import ApprovalError, NotFoundError
from groundwork.core.domain.harmonize import ApprovalItem, Decision, HarmonizedEmail
from groundwork.core.ports.approval import ApprovalPort
from tests.fakes import InMemoryApproval

ADAPTERS: dict[str, Callable[[Path], ApprovalPort]] = {
    "memory": lambda _: InMemoryApproval(),
    "file": lambda tmp_path: FileApproval("acme", tmp_path / "var"),
}


@pytest.fixture(params=sorted(ADAPTERS))
def approval(request: pytest.FixtureRequest, tmp_path: Path) -> ApprovalPort:
    return ADAPTERS[request.param](tmp_path)


def _item(id: str = "case-1", subject: str = "Your question") -> ApprovalItem:
    return ApprovalItem(
        id=id,
        contact_id="acme-c-1",
        recipient="ana.silva@example.com",
        email=HarmonizedEmail(subject=subject, body="Body.", rationale="Why."),
        decision=Decision(route="approval", reasons=("external emails need a human",)),
    )


def test_submit_returns_the_id_and_the_item_is_pending(approval: ApprovalPort) -> None:
    assert approval.submit(_item()) == "case-1"
    (pending,) = approval.list_pending()
    assert pending == _item()
    assert pending.status == "pending"


def test_nothing_is_pending_at_first(approval: ApprovalPort) -> None:
    assert approval.list_pending() == ()


def test_pending_items_are_listed_by_id(approval: ApprovalPort) -> None:
    for id in ("case-b", "case-c", "case-a"):
        approval.submit(_item(id))
    assert [i.id for i in approval.list_pending()] == ["case-a", "case-b", "case-c"]


def test_submitting_a_pending_item_again_replaces_it(approval: ApprovalPort) -> None:
    approval.submit(_item(subject="First"))
    approval.submit(_item(subject="Second"))
    (pending,) = approval.list_pending()
    assert pending.email.subject == "Second"


def test_approving_resolves_the_item_and_removes_it_from_pending(approval: ApprovalPort) -> None:
    approval.submit(_item())
    resolved = approval.resolve("case-1", approved=True)
    assert (resolved.status, resolved.reason) == ("approved", None)
    assert approval.list_pending() == ()


def test_rejecting_stores_the_reason(approval: ApprovalPort) -> None:
    approval.submit(_item())
    resolved = approval.resolve("case-1", approved=False, reason="wrong tone for this account")
    assert (resolved.status, resolved.reason) == ("rejected", "wrong tone for this account")
    assert approval.list_pending() == ()


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_rejecting_needs_a_reason_and_leaves_the_item_pending(
    approval: ApprovalPort, reason: str | None
) -> None:
    approval.submit(_item())
    with pytest.raises(ApprovalError, match="needs a reason"):
        approval.resolve("case-1", approved=False, reason=reason)
    assert [i.id for i in approval.list_pending()] == ["case-1"]


def test_resolving_an_unknown_id_raises_not_found(approval: ApprovalPort) -> None:
    with pytest.raises(NotFoundError, match="case-404"):
        approval.resolve("case-404", approved=True)


def test_resolving_twice_raises_and_keeps_the_first_answer(approval: ApprovalPort) -> None:
    approval.submit(_item())
    approval.resolve("case-1", approved=True)
    with pytest.raises(ApprovalError, match="already approved"):
        approval.resolve("case-1", approved=False, reason="changed my mind")


def test_a_resolved_item_cannot_be_submitted_again(approval: ApprovalPort) -> None:
    approval.submit(_item())
    approval.resolve("case-1", approved=False, reason="no")
    with pytest.raises(ApprovalError, match="already rejected"):
        approval.submit(_item())
