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

## Vector search
- Scope: interview transcripts, process docs, historical emails.
- Contextual Retrieval: Claude prepends a short context to each chunk before embedding.
- Hybrid search: embeddings (Voyage) + BM25, stored in LanceDB.
- Exposed to agents as the MCP tool `search_knowhow`.
