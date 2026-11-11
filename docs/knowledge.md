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

## Extraction pipeline
1. Interview transcript in `client_packs/<client>/interviews/`.
2. Claude extracts candidate rules with tool use and a strict JSON schema.
3. A human reviews and approves them in `rules.yaml`.
4. Rules without provenance are rejected by pack validation.

## Vector search
- Scope: interview transcripts, process docs, historical emails.
- Contextual Retrieval: Claude prepends a short context to each chunk before embedding.
- Hybrid search: embeddings (Voyage) + BM25, stored in LanceDB.
- Exposed to agents as the MCP tool `search_knowhow`.
