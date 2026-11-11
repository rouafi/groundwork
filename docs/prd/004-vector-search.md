# PRD-004: Vector search for know-how
Status: todo | Branch: `feat/vector-search` | Depends on: 002

## Goal
Make raw interview text searchable with hybrid retrieval and Contextual Retrieval, exposed as an MCP tool. This is the first PRD to cut if time is short.

## Why
Rules capture what experts decided; passages capture the nuance behind it. Facts stay in the ontology and are never embedded (ADR 0002).

## Read first
docs/knowledge.md, docs/adr/0002-ontology-for-facts-vectors-for-know-how.md, PRD-002.

## Scope
In: chunking, contextualization, embeddings, two vector store adapters, rank fusion, index artifact, `search_knowhow` tool.
Out: indexing CRM facts, reranking models, incremental indexing.

## Design
**Ports**
- `EmbeddingPort.embed(texts, input_type: document|query) -> list[list[float]]`
- `VectorStorePort`: `upsert(chunks)`, `vector_search(embedding, k)`, `keyword_search(query, k)`; both searches return ranked `SearchHit(chunk_id, doc_id, text, score)`.

**Adapters**: `VoyageEmbedding` (`voyageai`; model id in one constant, verify the current name in Voyage docs), `ReplayEmbedding` (recorded vectors keyed by sha256 of text and input type, in `traces/<pack>/embeddings/`), `InMemoryVectorStore` (tests), `LanceDbStore` (`lancedb`, built in a temporary directory at load).

**Chunking** in `core/services/chunking.py`: deterministic, paragraph-based, target about 200 words and at most 300. Each chunk carries `doc_id` and the interview role.

**Contextual Retrieval**: for each chunk, `ModelPort.complete_text` with the whole document as `cached_context` and an instruction to write a one- or two-sentence context situating the chunk in the document, answering with that context only. Embed and index `context + chunk`. Use the cheap model.

**Retrieval** in `core/services/retrieval.py`: run vector and keyword search, fuse with Reciprocal Rank Fusion (k = 60), return the top `k`. Fusion lives in the core so it is testable without LanceDB.

**Index artifact**: `groundwork index --pack acme` writes `client_packs/<client>/index/chunks.jsonl` (`id, doc_id, text, context, embedding`). Committed, diff-friendly. The vector store is built from it at startup.

**MCP tool**: `search_knowhow(query, k=5)` returns hits with `doc_id`, `text`, `score`. Read-only.

**Retrieval questions**: author `client_packs/<client>/retrieval.jsonl` with 10 items `{question, expected_doc_id, expected_quote}` for PRD-006.

## Files
`core/ports/{embedding,vector_store}.py`, `core/services/{chunking,retrieval}.py`, `adapters/{embedding,vector}/...`, `entrypoints/{mcp_server,cli}.py`, `client_packs/{acme,beta}/{index/chunks.jsonl,retrieval.jsonl}`, tests.

## Acceptance criteria
1. The `VectorStorePort` contract suite passes for both `InMemoryVectorStore` and `LanceDbStore`.
2. Chunking is deterministic: same input, same ids and boundaries (test).
3. Rank fusion has a unit test with hand-computed expected order.
4. `search_knowhow` works in replay with no environment variables.
5. `index` is idempotent: running it twice yields an identical `chunks.jsonl`.
6. Facts are never indexed (test: no chunk originates from fixtures).

## Tests
Unit: chunking, fusion, context prompt assembly. Contract: vector store. Integration: index then search on replay.

## Commit plan
1. `feat(ports): add EmbeddingPort and VectorStorePort`
2. `feat(knowledge): add deterministic chunking`
3. `feat(adapters): add in-memory vector store with contract tests`
4. `feat(adapters): add LanceDB vector store`
5. `feat(adapters): add Voyage and replay embedding adapters`
6. `feat(knowledge): add contextual retrieval and rank fusion`
7. `feat(cli): add index command and commit pack indexes`
8. `feat(mcp): add search_knowhow tool`
9. `docs: update knowledge and mark PRD-004 done`

## Risks and open questions
Embedding recordings need a real Voyage key once. If unavailable, stop and ask. Do not generate fake vectors for the demo.
