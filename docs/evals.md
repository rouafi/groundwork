# Evals

Question answered: can this agent write on behalf of this client's teams? Evals gate go-live.

**Where it stands (2026-11-13):** the machinery is complete and runs on replay, but neither synthetic pack meets its thresholds yet. `evals/report.md` has the numbers; the causes are under "What the first runs showed". Design decisions: [ADR 0010](adr/0010-evals-judge-calibration-replay.md).

## Level 1: automated, every commit
Golden set per client: `client_packs/<client>/golden.jsonl`, 20 cases (6 adversarial: wrong price, fabricated product, discount promise, unknown feature, 2 injections through the contact `notes`).

```json
{"id": "acme-007", "contact_id": "acme-c-1", "channel": "external", "draft": "...", "must_contain": ["1490"], "forbidden": ["regex"], "expected_route": "approval", "tags": ["realistic", "price"]}
```

`must_contain` and `forbidden` are optional. `expected_route` is `auto_send`, `approval` or `blocked`.

| Scorer | Type | Definition | Default threshold |
|---|---|---|---|
| `fact_false_claims` | deterministic | false claims from `check_claims`, plus every `must_contain` string that is missing | 0 |
| `rule_violations` | deterministic + judge | forbidden patterns hit, plus rules the judge marks `violated` | 0 |
| `tone_mean_min` | judge | mean tone from 1 to 5 against `rubric.md` | 4.0 |
| `routing_accuracy_min` | deterministic | decided route equals `expected_route` | 1.0 |
| `traceability_min` | deterministic | every cited node exists and every cited rule applies to the contact | 1.0 |
| `retrieval_recall_at_5_min` | deterministic | right passage in the top 5 of `retrieval.jsonl` | 0.8 |
| `judge_agreement_min` | deterministic | judge within one point of the human tone labels | 0.8 |

Thresholds live in `client_packs/<client>/thresholds.yaml`. Counts are maxima, `_min` values are minima. A pack that is below one does not ship. **Never lower a threshold to get green**: change the agent, the rubric or the data, or ask the client.

**Baseline.** The raw draft goes through the same scorers (a `PassthroughAgent`, ADR 0005), so the report shows before and after: false claims, forbidden hits and tone.

**The judge** (`domains/comms/prompts/judge_email.md` plus the pack's `rubric.md`) grades one email at a time: a tone from 1 to 5 and one verdict per applicable rule. It never grades facts or prices. It is calibrated first, on 5 emails per pack that a human labeled for tone (`judge_calibration.jsonl`: `id`, `subject`, `body`, `human_tone`): if it is within one point of fewer than `judge_agreement_min` of them, the run stops with "uncalibrated judge" before any case runs, so a bad judge costs 5 calls. Labels are never edited to make the judge pass. The judge model is the same family as the agent, which can favour the agent's own style (ADR 0010).

## What the first runs showed
After one prompt fix (the agent now applies the rules that match the contact, adds nothing the draft does not say, leaves no placeholders):

| | Raw draft | acme | beta | Threshold |
|---|---|---|---|---|
| False claims | 8 / 4 | 0 | 2 | 0 |
| Routing | | 1.00 | 0.90 | 1.00 |
| Tone mean | 2.35 / 2.00 | 3.75 | 3.10 | 4.0 |
| Rule violations | | 9 | 35 | 0 |

The agent beats the raw draft everywhere. What is left comes mostly from data the agent does not have, not from the model:
- beta's `r-001` asks for a signature with the contract reference and a title in the greeting; no fixture holds a contract reference or a sender identity (14 violations).
- beta's `r-020` asks to attach the site checklist; an email written by an agent cannot attach a file.
- acme's `r-012` asks to lead with the time the team saves; the CRM has no such fact and the agent may not invent one (6 of 9 violations).

Next steps, for a client: put the sender and the contract reference in the context pack, decide which rules an email cannot show (the judge may mark them `not_applicable`), then re-record. Retrieval recall@5 is 1.0 but the packs have 6 chunks each, so it shows the method, not production quality.

## Level 2: human, in production
External emails go through the approval queue. Tracked: approval rate without edits, edit size, rejection reasons. Every rejection becomes a new golden case. Gating internal auto-send on these evals is a follow-up: until it exists, `auto_send` stays a policy a pack can turn off (docs/security.md).

## Honesty rules
- Data is synthetic, and the README says so.
- `traces/` and `evals/report.md` come from real runs and are never edited by hand.
- A report without a timestamp, in stable order: the same recordings give the same bytes.

## Commands
- `make evals`: replay every golden set, no key. Exit 1 while a threshold is unmet (today: both packs).
- `groundwork evals --write-report`: regenerate `evals/report.md` and `evals/results/<pack>.json` (all packs).
- `groundwork evals --check-report`: fail if the committed report differs from a replay. `make check` runs it with `--allow-unmet-thresholds`, which prints the unmet thresholds without failing: remove that flag once the packs pass.
- `groundwork evals --model claude --record`: record every run afresh. Costs money (a few dollars for two packs; not measured) and needs `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY`; `--write-report` and `--check-report` need every pack.
- `groundwork evals --model claude --resume`: the same, but only the agent traces, judge calls and embeddings with no valid recording go live. Use it after an interrupted run or a one-case change. A change to a prompt makes every agent trace stale, so it re-records them all.
- With a Voyage account without a payment method, set `VOYAGE_RPM=3`. Anthropic server errors are retried 6 times.
- `--batch` (Message Batches API) is not implemented: replay makes it unnecessary and a pack is about 100 calls.
