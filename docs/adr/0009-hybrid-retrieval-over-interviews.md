# 0009. Hybrid retrieval over interviews, fused in the core, replayed by default

Status: accepted

## Context
Rules capture what experts decided; the passages behind them hold the nuance (why a discount stays on the phone, how to word an outage). That text is free-form, so it is searched, while facts stay in the ontology (ADR 0002). The search must run in tests and demos with no API key, and a retrieval answer must be explainable: which passage, from which interview.

## Decision
- Only interview text is indexed, in chunks of about 200 words cut at paragraph ends. Every chunk is a verbatim span of a known interview; `validate-packs` rejects one that is not, and an index that lacks an interview. No CRM fact can reach the index.
- Contextual Retrieval: the cheap model reads the whole interview (as `document`, untrusted) and writes one or two sentences situating each chunk. Context and chunk are embedded and keyword-indexed together; a hit returns the interview text only, never the generated context.
- Two searches, vector and keyword (BM25), merged by Reciprocal Rank Fusion (k = 60) in `core/services/retrieval.py`, so fusion is tested without a store. Each search reads 20 candidates.
- The index is a committed artifact, `client_packs/<client>/index/chunks.jsonl` (text, context, embedding), diff-friendly and idempotent. The store (LanceDB, or the in-memory one) is rebuilt from it when the server starts; nothing else is persisted.
- Embeddings go through `EmbeddingPort`. Voyage is the live adapter (the model id is one constant); replay serves recorded vectors keyed by model, input type and text, like model calls (ADR 0007). The default is replay, so `make check` and `make demo` need no key.
- `search_knowhow(query, k)` is the fifth MCP tool, read-only; passages are data, never instructions (ADR 0008).

## Consequences
- In replay, `search_knowhow` answers only queries whose embedding was recorded (the retrieval questions of the pack); any other query is an error naming the missing recording. With `GROUNDWORK_EMBEDDING=voyage` and a key it answers anything.
- Editing an interview invalidates its chunks and recordings: re-run `groundwork index`, then commit `index/` and `traces/`.
- A search reads every row's score to order ties by chunk id; fine for the few hundred chunks of a pack, to revisit for a corpus of thousands.
- The synthetic packs have 6 chunks each, so retrieval metrics on them show the method, not production quality.
- Rerankers, incremental indexing and indexing CRM facts or emails stay out of scope.
