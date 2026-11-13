"""The deterministic scorers: pure functions over what one run produced. No model.

Each takes a golden case and the outcome of the harmonization flow for it, and returns
a small result that the runner aggregates against the thresholds. The same scorers run
on the raw draft (through the passthrough agent) for the before/after comparison.
"""

import re
from collections.abc import Callable, Collection, Sequence

from groundwork.core.domain.evals import FactScore, GoldenCase, RetrievalScore, TraceabilityScore
from groundwork.core.domain.knowhow import Rule
from groundwork.core.domain.search import RetrievalQuestion, SearchHit
from groundwork.core.services.harmonize import HarmonizeOutcome

K = 5


def email_text(outcome: HarmonizeOutcome) -> str:
    """What the contact would read: the subject, then the body."""
    return f"{outcome.email.subject}\n{outcome.email.body}"


def fact_accuracy(case: GoldenCase, outcome: HarmonizeOutcome) -> FactScore:
    """False claims from the claim check, and every `must_contain` string the email lacks."""
    text = email_text(outcome).casefold()
    false_claims = sum(1 for c in outcome.claim_checks if c.status == "false")
    missing = tuple(s for s in case.must_contain if s.casefold() not in text)
    return FactScore(false_claims=false_claims, missing=missing)


def forbidden_hits(text: str, patterns: Sequence[str]) -> tuple[str, ...]:
    """The patterns, in the order given, that match somewhere in `text`."""
    return tuple(p for p in patterns if re.search(p, text))


def case_forbidden_hits(case: GoldenCase, outcome: HarmonizeOutcome) -> tuple[str, ...]:
    return forbidden_hits(email_text(outcome), case.forbidden)


def routing_ok(case: GoldenCase, outcome: HarmonizeOutcome) -> bool:
    """The harness decided the route the case expects."""
    return outcome.decision.route == case.expected_route


def traceability(
    case: GoldenCase, outcome: HarmonizeOutcome, rules: Sequence[Rule], known_nodes: Collection[str]
) -> TraceabilityScore:
    """Every cited node id exists, and every cited rule applies to this contact and channel.

    `known_nodes` are the ids of everything the agent may cite (rules, products, passages,
    the contact's own records); `rules` are the pack's rules, for their scope.
    """
    contact = outcome.context.contact_context
    scope_of = {r.id: r.scope for r in rules}
    cited = outcome.email.cited_nodes
    unknown = tuple(n for n in cited if n not in known_nodes)
    inapplicable = tuple(
        n
        for n in cited
        if n in scope_of
        and not scope_of[n].applies_to(
            case.channel, contact.company.segment, contact.contact.persona
        )
    )
    return TraceabilityScore(cited=cited, unknown=unknown, inapplicable=inapplicable)


def retrieval_recall(
    questions: Sequence[RetrievalQuestion], search: Callable[[str], Sequence[SearchHit]]
) -> RetrievalScore:
    """recall@5: a question is found when one of the top hits is the expected interview and
    holds the expected quote. `search` returns the hits for a query, best first."""
    missed = []
    for item in questions:
        quote = " ".join(item.expected_quote.split())
        hits = list(search(item.question))[:K]
        if not any(
            h.doc_id == item.expected_doc_id and quote in " ".join(h.text.split()) for h in hits
        ):
            missed.append(item.question)
    return RetrievalScore(
        k=K, found=len(questions) - len(missed), total=len(questions), missed=tuple(missed)
    )
