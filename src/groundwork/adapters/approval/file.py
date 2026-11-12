"""FileApproval: the ApprovalPort on one JSON file per item, `<root>/approvals/<pack>/<id>.json`.

A human reads the files, or uses `groundwork approvals`, to approve or reject. The files
are written atomically and are plain, sorted JSON.
"""

import os
import re
from pathlib import Path

from groundwork.core.domain.errors import ApprovalError, NotFoundError
from groundwork.core.domain.harmonize import ApprovalItem

APPROVALS_DIR = "approvals"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class FileApproval:
    def __init__(self, pack: str, root: Path = Path("var")) -> None:
        self._directory = root / APPROVALS_DIR / pack

    def submit(self, item: ApprovalItem) -> str:
        existing = self._find(item.id)
        if existing is not None and existing.status != "pending":
            raise ApprovalError(f"approval {item.id!r} is already {existing.status}")
        self._write(item.model_copy(update={"status": "pending", "reason": None}))
        return item.id

    def list_pending(self) -> tuple[ApprovalItem, ...]:
        if not self._directory.is_dir():
            return ()
        items = (self._load(path) for path in sorted(self._directory.glob("*.json")))
        return tuple(item for item in items if item.status == "pending")

    def resolve(self, id: str, approved: bool, reason: str | None = None) -> ApprovalItem:
        item = self._find(id)
        if item is None:
            raise NotFoundError("approval", id)
        if item.status != "pending":
            raise ApprovalError(f"approval {id!r} is already {item.status}")
        if not approved and not (reason and reason.strip()):
            raise ApprovalError(f"rejecting {id!r} needs a reason")
        resolved = item.model_copy(
            update={"status": "approved" if approved else "rejected", "reason": reason or None}
        )
        self._write(resolved)
        return resolved

    def _path(self, id: str) -> Path:
        if not _SAFE_ID.match(id):
            raise ApprovalError(f"invalid approval id {id!r}")
        return self._directory / f"{id}.json"

    def _find(self, id: str) -> ApprovalItem | None:
        path = self._path(id)
        return self._load(path) if path.is_file() else None

    def _load(self, path: Path) -> ApprovalItem:
        return ApprovalItem.model_validate_json(path.read_text(encoding="utf-8"))

    def _write(self, item: ApprovalItem) -> None:
        path = self._path(item.id)
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        body = item.model_dump_json(indent=2) + "\n"
        temporary.write_text(body, encoding="utf-8")
        os.replace(temporary, path)
