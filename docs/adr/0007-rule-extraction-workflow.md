# 0007. Rule extraction is a grounded workflow, not an agent

Status: accepted

## Context
Expert interviews must become rules a human can approve. Every rule has to point to what an expert really said, and the run has to show where experts disagree with each other or with the CRM. The steps are known in advance: read an interview, list its rules, classify them, check them, compare them across interviews.

Three API facts shaped the design (checked against the docs on 2026-11-12):
- Citations return the verbatim span the model relied on, with its character range, but cannot be combined with structured output (`output_config.format`) in one request.
- Forced `tool_choice` is rejected by current models, so structured output goes through `output_config.format`.
- Temperature is not accepted, so the same prompt can give different rules on two runs.

## Decision
- **A workflow in plain Python, not an agent and not a framework.** `core/services/extraction.py` runs fixed stages over `ModelPort`: ground (Sonnet, Citations), type (Haiku, structured output), filter (code), number, consolidate (Sonnet, structured output), claim check (code), coverage gaps (code), follow-up questions (Haiku). Interviews run in a bounded thread pool and are merged in sorted order. A failing interview or pack stage becomes a `Failure` in the report and the others continue.
- **The quote comes from the API, never from generated text.** Grounding uses Citations. Typing is a second call because Citations and structured output cannot be combined; it receives the cited statements by index and never rewrites a quote. A deterministic filter drops, with a reason, anything whose quote is not verbatim in the transcript or whose scope, products or claim do not fit the domain and the CRM.
- **Judgment goes to the model, checks go to code.** The model proposes duplicates and conflicts by rule id; code drops unknown ids, merges and renumbers. Coverage gaps and the claim check against the CRM are code only.
- **Determinism comes from record and replay, not from the model.** Every call is keyed by the sha256 of its inputs (method, model, effort, prompts, document, schema) and recorded under `traces/<pack>/model/`. Replay serves those recordings, never calls the network and fails loudly on a miss. A prompt change invalidates the recordings, which are then re-recorded by a human with a key.
- **The workflow only proposes.** It writes `rules.proposed.yaml` and `extraction_report.yaml`; a human approves rules in `rules.yaml` by a commit (ADR 0004).

## Consequences
- Every approved rule can be traced to a sentence of an interview, and `validate-packs` re-checks it at its exact range.
- Two model calls per interview instead of one. On the synthetic packs a run costs about 6 cents per client.
- Recordings are part of the repo: a prompt change is a visible diff in `traces/` and in the committed outputs, and `test_recorded_runs` fails until they are re-recorded.
- The claim check is a word-containment floor: it flags a `claim_text` that contains none of the product's allowed claims as whole words. It has two known limits, both left to the human review and to the semantic `check_claims` of PRD-003:
  - it flags paraphrases of allowed claims ("Setup takes one day" for "Setup in one day"), which are false positives;
  - it does not catch an extra promise written next to an allowed claim ("Single sign-on included, and a 50% discount"), which a test pins.
- An agent remains the right tool where the path is not known in advance: drafting emails (PRD-005).
