"""Domain errors. Adapters and services raise these; entrypoints turn them into messages."""


class GroundworkError(Exception):
    """Base class for every error groundwork raises on purpose."""


class NotFoundError(GroundworkError):
    """A requested object does not exist in the source system."""

    def __init__(self, kind: str, id: str) -> None:
        self.kind = kind
        self.id = id
        super().__init__(f"{kind} {id!r} not found")


class PackError(GroundworkError):
    """A client or domain pack is invalid: config, fixtures or references."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
