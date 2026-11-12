"""What a human does with the emails waiting for approval: approve and send, or reject.

An external email is only ever sent here, after a person approved it (ADR 0004). With
`harmonize`, this is the only other code that calls `MessagingPort` and `ApprovalPort`.
"""

from groundwork.core.domain.errors import MessagingError
from groundwork.core.domain.harmonize import ApprovalItem
from groundwork.core.ports.approval import ApprovalPort
from groundwork.core.ports.crm import CrmPort
from groundwork.core.ports.messaging import MessagingPort


def approve(
    id: str, approval: ApprovalPort, messaging: MessagingPort, crm: CrmPort
) -> ApprovalItem:
    """Record the approval, then send the email. An item can be approved once.

    If delivery fails, the approval stays recorded and the error says so: the email was
    not sent and must be sent by hand, never approved again.
    """
    item = approval.resolve(id, approved=True)
    try:
        messaging.send(item.email, crm.get_contact(item.contact_id))
    except MessagingError as exc:
        raise MessagingError(
            f"approval {id!r} is recorded but the email was not sent: {exc}"
        ) from exc
    return item


def reject(id: str, reason: str, approval: ApprovalPort) -> ApprovalItem:
    """Record the rejection and its reason. Nothing is sent."""
    return approval.resolve(id, approved=False, reason=reason)
