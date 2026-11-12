"""MemoryMessaging: a MessagingPort that keeps what it was asked to send, in memory.

For evals and tests: nothing leaves the process and nothing is written to disk.
"""

from groundwork.core.domain.harmonize import HarmonizedEmail


class MemoryMessaging:
    def __init__(self) -> None:
        self.sent: list[tuple[HarmonizedEmail, str]] = []

    def send(self, email: HarmonizedEmail, to: str) -> None:
        self.sent.append((email, to))
