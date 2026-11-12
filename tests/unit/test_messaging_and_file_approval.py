import json
from pathlib import Path

import pytest

from groundwork.adapters.approval.file import FileApproval
from groundwork.adapters.messaging.console import ConsoleMessaging
from groundwork.core.domain.errors import ApprovalError, MessagingError
from groundwork.core.domain.harmonize import ApprovalItem, Decision, HarmonizedEmail

TO = "ana.silva@example.com"
EMAIL = HarmonizedEmail(subject="Quote", body="Hello Ana.\n\nPro costs 1490.00 EUR.", rationale="r")


def test_console_messaging_prints_and_appends_to_the_outbox(tmp_path: Path) -> None:
    printed: list[str] = []
    messaging = ConsoleMessaging("acme", tmp_path / "var", echo=printed.append)
    messaging.send(EMAIL, TO)
    messaging.send(EMAIL, TO)
    assert printed[0] == (
        "To: ana.silva@example.com\nSubject: Quote\n\nHello Ana.\n\nPro costs 1490.00 EUR.\n"
    )
    lines = messaging.outbox.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {
        "to": TO,
        "subject": "Quote",
        "body": "Hello Ana.\n\nPro costs 1490.00 EUR.",
    }
    assert messaging.outbox == tmp_path / "var" / "outbox" / "acme.jsonl"


def test_console_messaging_reports_an_outbox_it_cannot_write(tmp_path: Path) -> None:
    blocker = tmp_path / "var"
    blocker.write_text("a file where the folder should be")
    with pytest.raises(MessagingError, match="cannot write the outbox"):
        ConsoleMessaging("acme", blocker, echo=lambda _: None).send(EMAIL, TO)


def _item(id: str) -> ApprovalItem:
    return ApprovalItem(
        id=id,
        contact_id="acme-c-1",
        recipient=TO,
        email=EMAIL,
        decision=Decision(route="approval", reasons=("external",)),
    )


def test_file_approval_writes_one_readable_json_file_per_item(tmp_path: Path) -> None:
    FileApproval("acme", tmp_path).submit(_item("case-1"))
    path = tmp_path / "approvals" / "acme" / "case-1.json"
    data = json.loads(path.read_text())
    assert data["status"] == "pending"
    assert data["email"]["subject"] == "Quote"
    assert not list(path.parent.glob("*.tmp"))


def test_file_approval_survives_a_new_instance(tmp_path: Path) -> None:
    FileApproval("acme", tmp_path).submit(_item("case-1"))
    again = FileApproval("acme", tmp_path)
    again.resolve("case-1", approved=False, reason="not today")
    resolved = json.loads((tmp_path / "approvals" / "acme" / "case-1.json").read_text())
    assert (resolved["status"], resolved["reason"]) == ("rejected", "not today")


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".hidden", "with space"])
def test_file_approval_refuses_an_id_that_could_leave_its_directory(
    tmp_path: Path, bad: str
) -> None:
    approval = FileApproval("acme", tmp_path)
    with pytest.raises(ApprovalError, match="invalid approval id"):
        approval.resolve(bad, approved=True)


def test_two_packs_do_not_share_a_queue(tmp_path: Path) -> None:
    FileApproval("acme", tmp_path).submit(_item("case-1"))
    assert FileApproval("beta", tmp_path).list_pending() == ()


def test_an_approval_file_that_is_not_valid_names_the_file_and_the_fix(tmp_path: Path) -> None:
    approval = FileApproval("acme", tmp_path)
    approval.submit(_item("case-1"))
    path = tmp_path / "approvals" / "acme" / "case-1.json"
    data = json.loads(path.read_text())
    del data["recipient"]
    path.write_text(json.dumps(data))
    with pytest.raises(ApprovalError) as error:
        approval.list_pending()
    assert str(path) in str(error.value)
    assert "recipient" in str(error.value) and "harmonize" in str(error.value)
