import pytest

from groundwork.core.domain.errors import ApprovalError, MessagingError, NotFoundError
from groundwork.core.domain.harmonize import ApprovalItem, Decision, HarmonizedEmail
from groundwork.core.services.approvals import approve, reject
from tests.fakes import InMemoryApproval, RecordingMessaging

EMAIL = HarmonizedEmail(subject="Quote", body="Pro costs 1490.00 EUR.", rationale="r")


def _queued() -> InMemoryApproval:
    approval = InMemoryApproval()
    approval.submit(
        ApprovalItem(
            id="case-1", contact_id="acme-c-1", recipient="ana.silva@example.com", email=EMAIL,
            decision=Decision(route="approval", reasons=("external",)),
        )
    )  # fmt: skip
    return approval


def test_approving_records_the_answer_then_sends_the_email_to_the_contact() -> None:
    approval, messaging = _queued(), RecordingMessaging()
    item = approve("case-1", approval, messaging)
    assert item.status == "approved"
    assert messaging.sent == [(EMAIL, "ana.silva@example.com")]
    assert approval.list_pending() == ()


def test_an_item_cannot_be_approved_twice_so_it_is_never_sent_twice() -> None:
    approval, messaging = _queued(), RecordingMessaging()
    approve("case-1", approval, messaging)
    with pytest.raises(ApprovalError, match="already approved"):
        approve("case-1", approval, messaging)
    assert len(messaging.sent) == 1


def test_approving_an_unknown_item_sends_nothing() -> None:
    messaging = RecordingMessaging()
    with pytest.raises(NotFoundError, match="case-404"):
        approve("case-404", _queued(), messaging)
    assert messaging.sent == []


def test_rejecting_stores_the_reason_and_sends_nothing() -> None:
    approval = _queued()
    item = reject("case-1", "wrong tone for this account", approval)
    assert (item.status, item.reason) == ("rejected", "wrong tone for this account")
    assert approval.list_pending() == ()


def test_a_rejection_without_a_reason_is_refused() -> None:
    with pytest.raises(ApprovalError, match="needs a reason"):
        reject("case-1", " ", _queued())


class _Failing:
    def send(self, email: HarmonizedEmail, to: str) -> None:
        raise MessagingError("outbox is full")


def test_a_delivery_failure_says_the_approval_is_recorded_and_the_email_was_not_sent() -> None:
    approval = _queued()
    with pytest.raises(MessagingError, match="recorded but the email was not sent: outbox is full"):
        approve("case-1", approval, _Failing())
    assert approval.list_pending() == ()
