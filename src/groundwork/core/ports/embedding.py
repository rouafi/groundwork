"""EmbeddingPort: turn texts into vectors.

Contract (tests/contracts/test_embedding_contract.py, run against every adapter
that can run without the network):
- One vector per text, in the input order; an empty input gives an empty list.
- Every vector has the same length.
- The same text and input type give the same vector.
"""

from collections.abc import Sequence
from typing import Literal, Protocol

InputType = Literal["document", "query"]


class EmbeddingPort(Protocol):
    """What the core may ask an embedding model."""

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        """Return one vector per text. Documents and queries are embedded differently."""
