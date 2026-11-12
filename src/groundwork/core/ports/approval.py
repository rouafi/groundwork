"""ApprovalPort: queue emails for a human, and record the human's answer.

Only the harmonize and approvals services call it. External emails always come here
(ADR 0004).

Contract (tests/contracts/test_approval_contract.py, run against every adapter):
- `submit` returns the item's id and the item is listed as pending; submitting a still
  pending item again replaces it, and submitting one already resolved raises
  `ApprovalError`.
- `list_pending` returns pending items only, in id order.
- `resolve` records the answer and the reason; an unknown id raises `NotFoundError`,
  and resolving an item twice raises `ApprovalError`.
- Resolving never sends anything: sending is the caller's decision.
"""

from typing import Protocol

from groundwork.core.domain.harmonize import ApprovalItem


class ApprovalPort(Protocol):
    """What the core may ask a queue of emails waiting for a human."""

    def submit(self, item: ApprovalItem) -> str:
        """Queue `item` as pending and return its id."""

    def list_pending(self) -> tuple[ApprovalItem, ...]:
        """Return the pending items, by id."""

    def resolve(self, id: str, approved: bool, reason: str | None = None) -> ApprovalItem:
        """Record the human's answer and return the resolved item."""
