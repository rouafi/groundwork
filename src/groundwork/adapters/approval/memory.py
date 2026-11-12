"""MemoryApproval: an ApprovalPort that keeps its queue in memory.

For evals and tests: nothing is written to disk. It follows the same contract as
FileApproval (tests/contracts/test_approval_contract.py).
"""

from groundwork.core.domain.errors import ApprovalError, NotFoundError
from groundwork.core.domain.harmonize import ApprovalItem


class MemoryApproval:
    def __init__(self) -> None:
        self._items: dict[str, ApprovalItem] = {}

    def submit(self, item: ApprovalItem) -> str:
        existing = self._items.get(item.id)
        if existing is not None and existing.status != "pending":
            raise ApprovalError(f"approval {item.id!r} is already {existing.status}")
        self._items[item.id] = item.model_copy(update={"status": "pending", "reason": None})
        return item.id

    def list_pending(self) -> tuple[ApprovalItem, ...]:
        return tuple(i for _, i in sorted(self._items.items()) if i.status == "pending")

    def resolve(self, id: str, approved: bool, reason: str | None = None) -> ApprovalItem:
        item = self._items.get(id)
        if item is None:
            raise NotFoundError("approval", id)
        if item.status != "pending":
            raise ApprovalError(f"approval {id!r} is already {item.status}")
        if not approved and not (reason and reason.strip()):
            raise ApprovalError(f"rejecting {id!r} needs a reason")
        resolved = item.model_copy(
            update={"status": "approved" if approved else "rejected", "reason": reason or None}
        )
        self._items[id] = resolved
        return resolved
