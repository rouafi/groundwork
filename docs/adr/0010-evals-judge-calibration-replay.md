# 0010. Evals: a calibrated judge, thresholds per pack, a report replayed in CI

Status: accepted

## Context
Whether an agent may write for a client has to be answered with numbers, the same way for every client, and without a paid API call on every commit. Facts can be checked by code (ADR 0004: claim checks and policies are not the model's job); tone and fit to the client's rules cannot, so a model has to judge them, and a judge is only worth what its agreement with people is.

## Decision
- **Deterministic first.** False claims (the claim check, plus `must_contain` strings), forbidden patterns, routing, traceability and retrieval are scored by code. Only tone and per-rule verdicts use a judge, and the judge is told never to grade facts or prices.
- **A calibrated judge.** The judge is a `ModelPort.complete_structured` call with a generic prompt plus the pack's own rubric, one email per call, the email passed as untrusted data. Before any case runs, it grades 5 emails per pack that a person labeled for tone; if it is within one point of fewer than `judge_agreement_min` (0.8), the run stops with an explicit "uncalibrated judge". Labels are never changed to pass the judge. The one time they were, it was the repo owner, who wrote the labels, who read the judge's reasons and agreed (acme: the hype email scored 1 and the jargon email 2, instead of the labels 3 and 4), and the change is committed as such.
- **Thresholds per pack** in `thresholds.yaml`, starting from the PRD's values (zero false claims, tone 4, routing 1). They are never lowered to get green.
- **Before and after.** The raw draft is scored by the same scorers through a passthrough agent, so the report shows what the agent changed.
- **Replayed in CI.** Agent traces, judge calls and embeddings are recorded once with the real models and replayed, so `make check` runs the evals offline and deterministically. The report and `evals/results/<pack>.json` have no timestamp and a stable order; `--check-report` fails if a committed file differs from a replay, so numbers cannot be edited or go stale unseen.
- **Recording is explicit and resumable.** `--record` re-runs everything; `--resume` replays what is valid and only runs what is missing or stale (a trace is stale when the request, the prompt or the context pack changed), because a live run of about 100 calls per pack was lost twice to provider errors and a rate limit before this existed. Anthropic calls retry 6 times on server errors; `VOYAGE_RPM` paces a Voyage account without a payment method.
- **Unmet thresholds do not fail `make check` yet.** `make check` runs `evals --check-report --allow-unmet-thresholds`: drift fails, unmet thresholds are printed. `make evals` stays strict. The flag is the visible marker of an open gap and is removed when the packs pass.

## Consequences
- **Both packs are below their thresholds today** (acme: tone 3.75, 9 violations; beta: tone 3.10, 2 false claims, 35 violations; see `evals/report.md`). The shortfall is mostly data the agent lacks (sender identity, contract reference, a time-saved fact) and rules an email cannot show (attach a file), not model quality. The machinery stands; shipping a pack waits on its context.
- **Self-preference.** The judge is Sonnet 5.5 and the agent is Sonnet 5.5: the judge may favour the agent's style. The calibration labels and the deterministic scorers are the check on that; a judge from another family is the remedy if it matters.
- **Small samples.** 20 cases and 5 calibration emails per pack are enough to show the method and catch large regressions, not to estimate a rate. Retrieval recall@5 is 1.0 on 6 chunks per pack, which shows the method only.
- **Re-recording is paid and slow.** A prompt change makes every agent trace stale: a full run per pack, plus the 3 demo cases per pack. The recordings are committed, so a change that touches one is visible in the diff.
- **Out of scope:** the Message Batches API (replay makes it unnecessary), level-2 production analytics, and gating internal auto-send on the evals (a follow-up).
