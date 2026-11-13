"""Run the evals of one pack: every golden case through the harness, and the raw draft.

For each case the flow runs twice, with the same claim check and the same scorers: once
with the real agent (the harmonized email) and once with the passthrough agent (the raw
draft), so the report can show before and after. Nothing is sent or queued: the flows
the caller builds use in-memory messaging and approval. Before any case runs, the judge
must be calibrated against the human labels, or the run fails.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from groundwork.core.domain.evals import (
    CalibrationCase,
    CaseResult,
    GoldenCase,
    PackMetrics,
    PackResult,
    RawResult,
    Thresholds,
)
from groundwork.core.domain.harmonize import HarmonizedEmail, HarmonizeRequest
from groundwork.core.domain.knowhow import Rule
from groundwork.core.domain.search import RetrievalQuestion, SearchHit
from groundwork.core.ports.model import ModelPort
from groundwork.core.services.evals.judge import calibrate, judge_email, require_calibrated
from groundwork.core.services.evals.scorers import (
    case_forbidden_hits,
    fact_accuracy,
    forbidden_hits,
    retrieval_recall,
    traceability,
)
from groundwork.core.services.evals.thresholds import check_thresholds
from groundwork.core.services.harmonize import HarmonizeFlow, HarmonizeOutcome, harmonize
from groundwork.core.services.rules import applicable_rules

RAW_SUBJECT = "(no subject)"


@dataclass(frozen=True)
class EvalDeps:
    """What the evals of one pack need. Both flows share the CRM, rules and claim check."""

    pack: str
    cases: Sequence[GoldenCase]
    thresholds: Thresholds
    calibration: Sequence[CalibrationCase]
    flow: HarmonizeFlow
    raw_flow: HarmonizeFlow
    judge_model: ModelPort
    judge_system: str
    rules: Sequence[Rule]
    known_nodes: frozenset[str]
    questions: Sequence[RetrievalQuestion] = ()
    search: Callable[[str], Sequence[SearchHit]] | None = None


def run_pack(deps: EvalDeps) -> PackResult:
    """Calibrate the judge, run every case, aggregate and check the thresholds.

    Raises `UncalibratedJudgeError` before running a case if the judge disagrees with the
    human labels too often.
    """
    agreement, _ = calibrate(deps.judge_model, deps.judge_system, deps.calibration)
    require_calibrated(agreement, deps.thresholds.judge_agreement_min)
    results = tuple(_run_case(deps, case) for case in deps.cases)

    retrieval = None
    notes: list[str] = []
    if deps.questions and deps.search is not None:
        retrieval = retrieval_recall(deps.questions, deps.search)
    else:
        notes.append("retrieval was not measured: the pack has no index or no retrieval questions")

    metrics = _metrics(results, retrieval.recall if retrieval else None, agreement.rate)
    return PackResult(
        pack=deps.pack,
        cases=results,
        metrics=metrics,
        thresholds=check_thresholds(deps.thresholds, metrics),
        retrieval=retrieval,
        agreement=agreement,
        notes=tuple(notes),
    )


def _run_case(deps: EvalDeps, case: GoldenCase) -> CaseResult:
    request = HarmonizeRequest(
        contact_id=case.contact_id, channel=case.channel, draft=case.draft, case_id=case.id
    )
    outcome = harmonize(deps.flow, request)
    raw = harmonize(deps.raw_flow, request)

    contact = outcome.context.contact_context
    applicable = applicable_rules(
        deps.rules, case.channel, contact.company.segment, contact.contact.persona
    )
    patterns = getattr(deps.flow.policies.forbidden_patterns, case.channel)
    judged = judge_email(
        deps.judge_model, deps.judge_system, outcome.email, case.channel,
        contact.company.segment, contact.contact.persona, applicable,
    )  # fmt: skip
    raw_email = HarmonizedEmail(subject=RAW_SUBJECT, body=case.draft, rationale="raw draft")
    raw_judged = judge_email(
        deps.judge_model, deps.judge_system, raw_email, case.channel,
        contact.company.segment, contact.contact.persona, applicable,
    )  # fmt: skip

    own_records = {contact.contact.id, contact.company.id, *(d.id for d in contact.deals)}
    hits = (*case_forbidden_hits(case, outcome), *forbidden_hits(_text(outcome), patterns))
    return CaseResult(
        id=case.id,
        tags=case.tags,
        channel=case.channel,
        expected_route=case.expected_route,
        route=outcome.decision.route,
        facts=fact_accuracy(case, outcome),
        forbidden_hits=tuple(dict.fromkeys(hits)),
        traceability=traceability(case, outcome, deps.rules, deps.known_nodes | own_records),
        tone=judged.verdict.tone,
        tone_reason=judged.verdict.tone_reason,
        rule_violations=judged.verdict.violations,
        raw=RawResult(
            route=raw.decision.route,
            false_claims=sum(1 for c in raw.claim_checks if c.status == "false"),
            forbidden_hits=tuple(
                dict.fromkeys(
                    (
                        *forbidden_hits(case.draft, case.forbidden),
                        *forbidden_hits(case.draft, patterns),
                    )
                )
            ),
            tone=raw_judged.verdict.tone,
            rule_violations=raw_judged.verdict.violations,
        ),
    )


def _text(outcome: HarmonizeOutcome) -> str:
    return f"{outcome.email.subject}\n{outcome.email.body}"


def _metrics(results: Sequence[CaseResult], recall: float | None, agreement: float) -> PackMetrics:
    n = len(results)

    def share(count: int) -> float:
        return round(count / n, 4) if n else 0.0

    def mean(values: Sequence[int]) -> float:
        return round(sum(values) / n, 4) if n else 0.0

    return PackMetrics(
        cases=n,
        fact_false_claims=sum(r.facts.false_claims + len(r.facts.missing) for r in results),
        rule_violations=sum(len(r.forbidden_hits) + len(r.rule_violations) for r in results),
        tone_mean=mean([r.tone for r in results]),
        routing_accuracy=share(sum(1 for r in results if r.routing_ok)),
        traceability=share(sum(1 for r in results if r.traceability.passed)),
        retrieval_recall_at_5=round(recall, 4) if recall is not None else None,
        judge_agreement=round(agreement, 4),
        raw_false_claims=sum(r.raw.false_claims for r in results),
        raw_forbidden_hits=sum(len(r.raw.forbidden_hits) for r in results),
        raw_tone_mean=mean([r.raw.tone for r in results]),
    )
