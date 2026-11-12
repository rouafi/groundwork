"""Real calls to the Voyage API. Manual only: `uv run pytest -m live`. Never run in CI."""

import os

import pytest
import voyageai

from groundwork.adapters.embedding.voyage import VoyageEmbedding

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY"),
]


def test_documents_and_queries_embed_to_vectors_of_one_size() -> None:
    embedding = VoyageEmbedding(voyageai.Client())
    documents = embedding.embed(["We never put a discount in writing."], "document")
    queries = embedding.embed(["Can we offer a discount by email?"], "query")
    assert len(documents) == len(queries) == 1
    assert len(documents[0]) == len(queries[0]) > 0
