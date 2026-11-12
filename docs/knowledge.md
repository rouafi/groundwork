# Knowledge

Two ontologies that talk, plus vector search for raw know-how.

## Facts ontology (structured)
Source: the client's systems through `CrmPort`. Entities: Company, Contact, Deal, Product, Segment, Persona. Facts are the source of truth for names, prices and deal stages. Facts are never embedded in the vector store.

## Know-how ontology (unstructured, made structured)
Source: expert interviews and process documents.
Each rule carries:
- `statement`: what to do or avoid
- `scope`: internal / external, segment, persona
- `provenance`: interview id and the supporting quote
- `status`: proposed / approved (a human approves every rule)

## Bridge
Shared concepts (Product, Segment, Persona) link facts and rules, so the agent can answer: what can I say to this contact, and how?

## Extraction workflow (ADR 0007)
`groundwork extract-rules --pack <client>` turns the interviews in `client_packs/<client>/interviews/` into proposals. Stages, in `core/services/extraction.py`:
1. **Ground** (extraction model, Citations): the interview is a document; the model lists one rule per situation and the API returns the verbatim sentences each rule relies on.
2. **Type** (cheap model, structured output): kind, scope, products and `claim_text` for each cited statement, by index. Quotes are never regenerated.
3. **Filter** (code): drops, with a reason, a quote not verbatim in the transcript, a scope outside the vocabulary, an unknown product, a `claim_text` on a non-claim rule.
4. **Consolidate** (extraction model, structured output): proposes duplicates, merged with every provenance, and conflicts between experts, flagged for the human.
5. **Check** (code): claims against the products' `allowed_claims`, coverage gaps (audiences with CRM contacts and no specific rule), then at most 5 follow-up questions.

Outputs: `rules.proposed.yaml` and `extraction_report.yaml` (dropped, conflicts, contradictions, gaps, questions, failures, cost per stage), plus the golden checks of `evals/extraction_golden.yaml`. A human copies the rules they approve into `rules.yaml` with `status: approved`; the workflow never writes it.

`validate-packs` re-checks every approved rule: each quote verbatim at its range in its interview, scope in the vocabulary, products known, and no claim outside `allowed_claims`.

Runs are recorded under `traces/<client>/model/` and replayed offline. To re-record after a prompt change (costs a few cents): delete `traces/<client>/`, then run `GROUNDWORK_MODEL=claude GROUNDWORK_RECORD=1 uv run --env-file .env groundwork extract-rules --pack <client>` and commit the traces with the outputs.

What to expect after a re-recording:
- The model is not deterministic, so the proposals change: rule ids can shift and no longer match `rules.yaml`. Review the new `rules.proposed.yaml` and update `rules.yaml` by hand; `validate-packs` re-checks every approved quote.
- The golden checks can fail. A failure means the prompt or the run needs a look, not that the golden data should be edited to pass.
- Most contradictions on the synthetic packs are paraphrases of allowed claims (false positives); a contradiction is a question for the reviewer, not a verdict. The claim check also does not see an extra promise written next to an allowed claim (ADR 0007), so read every approved claim.
- Without `--out-dir`, the run writes into the pack, including when it fails (for example a replay miss after a prompt edit): restore the committed outputs with `git checkout client_packs/<client>/` if needed.
- The cost line is in tokens per stage, not in money.

## Vector search (ADR 0009)
Scope: interview transcripts. CRM facts are never indexed, and `validate-packs` fails an index whose chunk is not a verbatim span of an interview.
- `groundwork index --pack <client>` chunks each interview (about 200 words, paragraph ends), has the cheap model write a one- or two-sentence context per chunk (Contextual Retrieval), embeds context and chunk, and writes `index/chunks.jsonl`. Running it twice gives the same file.
- Search is hybrid: vector (Voyage embeddings) and keyword (BM25), fused with Reciprocal Rank Fusion (k = 60) in the core. LanceDB is built from `chunks.jsonl` when the server starts.
- Exposed to agents as the MCP tool `search_knowhow(query, k=5)` (docs/mcp.md). A hit is the interview text, its interview id and a score.
- `retrieval.jsonl` holds 10 questions per pack, each with the interview and a verbatim quote a search must find: the input of the retrieval evals (PRD-006).

Embeddings and contexts are recorded under `traces/<client>/embeddings/` and `traces/<client>/model/` and replayed offline, like rule extraction. Replay answers only recorded queries; to record (a few cents, needs `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY`), delete `traces/<client>/embeddings/` and the contextualize recordings, then run `GROUNDWORK_MODEL=claude GROUNDWORK_EMBEDDING=voyage GROUNDWORK_RECORD=1 uv run --env-file .env groundwork index --pack <client>` and commit `index/` and `traces/`. After editing an interview, re-run it the same way.
