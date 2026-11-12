"""MessagingPort: send an email to an address.

Only the harmonize and approvals services call it, and they choose the address: an
external email goes to the contact and only after a human approved it; an internal one
goes to the pack's internal address, never to a customer (ADR 0004). No adapter may
send on its own.

Contract (tests/contracts/test_messaging_contract.py, run against every adapter):
`send` delivers one email to `to`, exactly as given, and raises `GroundworkError` if it
cannot. Sending twice delivers twice.
"""

from typing import Protocol

from groundwork.core.domain.harmonize import HarmonizedEmail


class MessagingPort(Protocol):
    """What the core may ask a channel that delivers email."""

    def send(self, email: HarmonizedEmail, to: str) -> None:
        """Deliver `email` to the address `to`."""
