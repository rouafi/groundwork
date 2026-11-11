# Evals

Question answered: can this agent write on behalf of this client's teams? Evals gate go-live.

## Level 1: automated, every commit
Golden set per client: `client_packs/<client>/golden.jsonl`, about 20 cases.

```json
{"id": "acme-007", "contact_id": "c_042", "channel": "external", "draft": "...", "must_contain": ["49"], "forbidden": ["regex"], "expected_route": "approval", "tags": ["false-claim"]}
```

| Scorer | Type | Target |
|---|---|---|
| Fact accuracy vs CRM | deterministic | 0 false facts |
| Rule compliance | deterministic + Claude | per pack threshold |
| Tone | Claude judge, rubric from the pack | per pack threshold |
| Routing (auto / approval / blocked) | deterministic | 100% |
| Traceability (cited nodes exist and support the text) | deterministic | 100% |
| Retrieval (right passage in top-k) | deterministic | recall@5 per pack |

Thresholds live in `client_packs/<client>/thresholds.yaml`. Below threshold, CI fails and the pack does not ship.
The Claude judge is calibrated on 5 human-labeled cases per pack. Judge runs use the Batch API.

## Level 2: human, in production
External emails go through the approval queue. Tracked: approval rate without edits, edit size, rejection reasons. Every rejection becomes a new golden case.

## Honesty rules
- Data is synthetic, and the README says so.
- `traces/` and `evals/report.md` are produced by real runs and never edited by hand.

## Commands
- `make evals`: run all golden sets (replay model by default)
- `GROUNDWORK_MODEL=claude make evals`: real run, regenerates the report
