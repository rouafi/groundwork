"""Domain errors. Adapters and services raise these; entrypoints turn them into messages."""


class GroundworkError(Exception):
    """Base class for every error groundwork raises on purpose."""


class NotFoundError(GroundworkError):
    """A requested object does not exist in the source system."""

    def __init__(self, kind: str, id: str) -> None:
        self.kind = kind
        self.id = id
        super().__init__(f"{kind} {id!r} not found")


class ModelError(GroundworkError):
    """A model call could not produce a usable answer."""


class ReplayMissError(ModelError):
    """Replay mode has no recording for this call. Never falls back to a live call."""

    def __init__(self, key: str, path: str) -> None:
        self.key = key
        super().__init__(
            f"no recording for model call {key} (expected {path}). "
            "Record it with GROUNDWORK_MODEL=claude GROUNDWORK_RECORD=1, then commit traces/."
        )


class ModelRefusalError(ModelError):
    """The model declined the request."""

    def __init__(self, category: str | None) -> None:
        self.category = category
        super().__init__(f"model refused the request (category: {category or 'unspecified'})")


class PackError(GroundworkError):
    """A client or domain pack is invalid: config, fixtures or references."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EmbeddingMissError(ModelError):
    """Replay mode has no recorded vector for this text. Never falls back to a live call."""

    def __init__(self, key: str, path: str) -> None:
        self.key = key
        super().__init__(
            f"no recording for embedding {key} (expected {path}). Replay answers only "
            "recorded texts, such as the pack's retrieval questions. To search any query, "
            "set GROUNDWORK_EMBEDDING=voyage and VOYAGE_API_KEY; to record a text for replay, "
            "add GROUNDWORK_RECORD=1 and commit traces/."
        )


class AgentError(GroundworkError):
    """The agent could not produce a usable email. Nothing is sent or queued."""


class AgentLimitError(AgentError):
    """The agent run went past a hard limit (steps, tokens or time) and was aborted."""

    def __init__(self, limit: str, detail: str) -> None:
        self.limit = limit
        super().__init__(f"agent aborted: {limit} limit exceeded ({detail})")


class ApprovalError(GroundworkError):
    """An approval cannot be submitted or resolved in its current state."""
