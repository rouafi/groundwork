"""MessagingPort: send an email to a contact.

Only the harmonize and approvals services call it: an external email is sent only after
a human approved it (ADR 0004). No adapter may send on its own.

Contract: `send` delivers one email to the contact's address, exactly as given, and
raises `GroundworkError` if it cannot. Sending twice delivers twice.
"""

from typing import Protocol

from groundwork.core.domain.facts import Contact
from groundwork.core.domain.harmonize import HarmonizedEmail


class MessagingPort(Protocol):
    """What the core may ask a channel that delivers email."""

    def send(self, email: HarmonizedEmail, contact: Contact) -> None:
        """Deliver `email` to `contact`."""
