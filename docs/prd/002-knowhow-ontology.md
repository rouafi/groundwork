# PRD-002: Know-how ontology and rule extraction
Status: todo | Branch: `feat/knowhow-ontology` | Depends on: 001

## Goal
Turn expert interviews into approved rules that carry provenance, through a `ModelPort` with recorded replay. After this PR each pack has `rules.yaml` produced by a real extraction run and reviewed by a human.

## Why
This is the Juno pattern made reusable: tacit know-how captured through LLM-assisted interviews, then validated by experts before it influences anything.

## Read first
CLAUDE.md, docs/knowledge.md, docs/security.md, docs/adr/0002-ontology-for-facts-vectors-for-know-how.md.

## Scope
In: know-how domain types, `ModelPort`, `ClaudeModel`, `ReplayModel` with recording, extraction service, synthetic interviews, `rules.yaml`, pack validation of rules.
Out: vector search (004), claim checking (003), the drafting agent (005).

## Design
**Domain** in `core/domain/knowhow.py`:
- `Scope(channel: internal|external|any = any, segments=(), personas=())`
- `Provenance(interview_id, quote)`
- `Rule(id, kind: tone|claim|practice, statement, scope, provenance, status: proposed|approved)`
- `Interview(id, role, text)`

**Port** in `core/ports/model.py`:
- `complete_structured(*, system, user, schema: type[T], cached_context=None) -> T`
- `complete_text(*, system, user, cached_context=None) -> str`

**ClaudeModel** (`adapters/model/claude.py`): official `anthropic` SDK. Structured output = force one tool call (`tool_choice`) whose `input_schema` is `schema.model_json_schema()`, then validate with Pydantic and retry once on validation error. `cached_context` is sent as a content block with `cache_control` (ephemeral). Model ids live in one constants block (defaults: `claude-sonnet-5-5` for extraction, `claude-haiku-5-5` for cheap tasks), overridable by env; verify the ids against docs.claude.com while implementing. Reads `ANTHROPIC_API_KEY`; never logs it.

**ReplayModel**: serves recorded calls keyed by sha256 of the canonical JSON (sorted keys) of `{system, user, schema_name, schema_json, cached_context}`. A miss raises `ReplayMissError` that names the key and the command to record; it never falls back to a live call.

**Recording**: with `GROUNDWORK_RECORD=1`, `ClaudeModel` writes each call to `traces/<pack>/model/<key>.json` (inputs and response only; no keys, no headers). If a prompt or schema changes, recordings must be regenerated.

**Extraction** in `core/services/extraction.py`: `extract_rules(interview, domain_pack, model) -> ExtractionResult(rules, dropped)`. The prompt is `domains/comms/prompts/extract_rules.md`, rendered with the domain vocabulary. The model returns candidates `{kind, statement, scope, quote}`. Deterministic post-filter drops a candidate when its quote is not a verbatim substring of the transcript (whitespace-normalized), its scope is outside the vocabulary, or its statement is empty. Ids are `<pack>-r-<nnn>`, status is always `proposed`, and `dropped` records each reason.

**Interviews** in `client_packs/<client>/interviews/*.md`: YAML front matter (`id`, `role`) then transcript. 3 per client, 300 to 500 words each, synthetic. Together they must contain 6 to 10 extractable practices per client, including at least 2 `claim` rules (for example never state a discount in external emails; always quote the CRM list price), at least 2 tone rules that differ between clients, and for `beta` at least 1 rule that overrides the domain default tone (formal to casual for `smb`).

**rules.yaml**: list of `Rule` dicts. Only `approved` rules are used downstream. Approval is a human editing `status: approved` in a commit.

**CLI**: `groundwork extract-rules --pack acme [--out rules.proposed.yaml]`. It never writes `rules.yaml`.

**Pack validation** adds: every approved rule has a provenance quote found verbatim in the referenced interview, scope values are in the vocabulary, rule ids are unique.

## Files
`core/domain/knowhow.py`, `core/ports/model.py`, `core/services/extraction.py`, `adapters/model/{claude,replay}.py`, `domains/comms/prompts/extract_rules.md`, `client_packs/{acme,beta}/{interviews/*.md,rules.yaml}`, `traces/{acme,beta}/model/*.json`, tests.

## Acceptance criteria
1. `groundwork extract-rules --pack acme` runs on `ReplayModel` with no environment variables and reproduces the recorded candidates.
2. A candidate whose quote is not in the transcript is dropped and reported (unit test with a stub model).
3. `validate-packs` fails when an approved rule cites a quote that is absent from its interview (test).
4. A replay miss raises `ReplayMissError`; no code path calls the network in replay mode (test that asserts it).
5. Each pack has an approved `rules.yaml` with at least 6 rules; `beta` includes the tone override.
6. `ClaudeModel` is covered by unit tests with a fake SDK client; one `live`-marked test exists but is never run in CI.

## Tests
Unit: filtering, hashing and keying, schema retry, vocabulary checks. Contract: `ModelPort` suite (stub, replay). Integration: CLI on replay.

## Commit plan
1. `feat(domain): add know-how types`
2. `feat(ports): add ModelPort`
3. `feat(adapters): add replay model with recording keys`
4. `feat(adapters): add Claude model adapter with forced tool-use output`
5. `feat(knowledge): add rule extraction service with provenance filter`
6. `feat(packs): add synthetic interviews for acme and beta`
7. `feat(cli): add extract-rules command and validate rules in validate-packs`
8. `feat(packs): add recorded extraction runs and reviewed rules`
9. `docs: update knowledge and mark PRD-002 done`

## Risks and open questions
Recordings only come from a real run (`GROUNDWORK_MODEL=claude GROUNDWORK_RECORD=1`). If the author has no API key available, stop and ask; do not fabricate recordings.
