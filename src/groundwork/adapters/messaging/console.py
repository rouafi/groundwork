"""ConsoleMessaging: the MessagingPort for demos and tests. It sends nothing anywhere.

Each "sent" email is printed and appended as one JSON line to `<root>/outbox/<pack>.jsonl`,
so a demo shows what would have been delivered and a test can read it back.
"""

import json
from collections.abc import Callable
from pathlib import Path

from groundwork.core.domain.errors import MessagingError
from groundwork.core.domain.harmonize import HarmonizedEmail

OUTBOX_DIR = "outbox"


class ConsoleMessaging:
    def __init__(
        self, pack: str, root: Path = Path("var"), echo: Callable[[str], None] = print
    ) -> None:
        self._path = root / OUTBOX_DIR / f"{pack}.jsonl"
        self._echo = echo

    @property
    def outbox(self) -> Path:
        return self._path

    def send(self, email: HarmonizedEmail, to: str) -> None:
        line = json.dumps(
            {
                "to": to,
                "subject": email.subject,
                "body": email.body,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as outbox:
                outbox.write(line + "\n")
        except OSError as exc:
            raise MessagingError(f"cannot write the outbox {self._path}: {exc}") from exc
        self._echo(f"To: {to}\nSubject: {email.subject}\n\n{email.body}\n")
