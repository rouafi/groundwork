# PRD-004: Vector search for know-how
Status: done | Branch: `feat/vector-search` | Depends on: 002

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

## Implementation notes
- `ModelPort.complete_text` has no `cached_context`: the whole interview goes as `document`, which already carries untrusted text as a separate block. The contextualization prompt is `domains/comms/prompts/contextualize.md`.
- A chunk is a verbatim span of its interview (paragraphs joined by a blank line), a short last chunk of under 60 words joins the previous one when it fits, and `validate-packs` rejects a chunk that is not in its interview or an index that lacks an interview. That is how criterion 6 is enforced for every pack, besides the integration test.
- The pack config gains `embedding: replay | voyage` (default `replay`, overridable by `GROUNDWORK_EMBEDDING`); `vector_store` accepts `lancedb` and `memory`. The Voyage model id is `voyage-4`, one constant in `adapters/embedding/voyage.py`.
- `groundwork index` also embeds the pack's `retrieval.jsonl` questions as queries, so recording covers them. In replay, `search_knowhow` answers those and any query recorded before; other queries are an error naming the missing recording (ADR 0009).
- Client packs may now hold `.jsonl` (the index and the retrieval questions): the data-only test accepts JSON Lines next to JSON, YAML and Markdown.
- Voyage limits an account without a payment method to 3 requests per minute; recording a second pack right after the first can hit it. Wait a minute and re-run, with `GROUNDWORK_MODEL=replay` so the recorded contexts are not paid for again.
