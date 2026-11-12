"""MessagingPort contract: one suite, every adapter.

Each adapter comes with a way to read back what it delivered. To cover a new adapter,
add a factory to `ADAPTERS` returning the port and that reader.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from groundwork.adapters.messaging.console import ConsoleMessaging
from groundwork.core.domain.harmonize import HarmonizedEmail
from groundwork.core.ports.messaging import MessagingPort
from tests.fakes import RecordingMessaging

Delivered = Callable[[], list[tuple[str, str, str]]]
TO = "handoffs@acme.example"
EMAIL = HarmonizedEmail(subject="Quote", body="Hello.\n\nPro costs 1490.00 EUR.", rationale="r")


def _console(tmp_path: Path) -> tuple[MessagingPort, Delivered]:
    port = ConsoleMessaging("acme", tmp_path / "var", echo=lambda _: None)

    def delivered() -> list[tuple[str, str, str]]:
        if not port.outbox.is_file():
            return []
        rows = [json.loads(line) for line in port.outbox.read_text().splitlines()]
        return [(r["to"], r["subject"], r["body"]) for r in rows]

    return port, delivered


def _recording(_: Path) -> tuple[MessagingPort, Delivered]:
    port = RecordingMessaging()
    return port, lambda: [(to, e.subject, e.body) for e, to in port.sent]


ADAPTERS: dict[str, Callable[[Path], tuple[MessagingPort, Delivered]]] = {
    "console": _console,
    "recording": _recording,
}


@pytest.fixture(params=sorted(ADAPTERS))
def messaging(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[MessagingPort, Delivered]:
    return ADAPTERS[request.param](tmp_path)


def test_nothing_is_delivered_until_send_is_called(
    messaging: tuple[MessagingPort, Delivered],
) -> None:
    assert messaging[1]() == []


def test_send_delivers_the_email_to_the_address_exactly_as_given(
    messaging: tuple[MessagingPort, Delivered],
) -> None:
    port, delivered = messaging
    assert port.send(EMAIL, TO) is None
    assert delivered() == [(TO, "Quote", "Hello.\n\nPro costs 1490.00 EUR.")]


def test_sending_twice_delivers_twice(messaging: tuple[MessagingPort, Delivered]) -> None:
    port, delivered = messaging
    port.send(EMAIL, TO)
    port.send(EMAIL, "someone.else@acme.example")
    assert [to for to, _, _ in delivered()] == [TO, "someone.else@acme.example"]
