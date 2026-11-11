# 0002. Ontology for facts, vectors for know-how

Status: accepted

## Context
Facts (prices, names, deal stages) must be exact. Know-how (tone, practices) lives in free text.

## Decision
Facts stay in a typed ontology fed by the CRM and are never embedded. Know-how is extracted into rules with provenance, and the raw text is searchable through hybrid vector search with Contextual Retrieval.

## Consequences
Claims can be checked deterministically. Two stores to maintain, accepted.
