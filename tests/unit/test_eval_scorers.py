from groundwork.core.domain.claims import ClaimCheck
from groundwork.core.domain.evals import GoldenCase
from groundwork.core.domain.harmonize import ContextPack, Decision, HarmonizedEmail
from groundwork.core.domain.search import RetrievalQuestion, SearchHit
from groundwork.core.services.evals.scorers import (
    case_forbidden_hits,
    fact_accuracy,
    forbidden_hits,
    retrieval_recall,
    routing_ok,
    traceability,
)
from groundwork.core.services.harmonize import HarmonizeOutcome
from groundwork.core.services.packs import load_rules
from tests.unit.conftest import ACME


def _case(**fields: object) -> GoldenCase:
    base = {
        "id": "acme-001",
        "contact_id": "acme-c-1",
        "channel": "external",
        "draft": "Hi.",
        "expected_route": "approval",
    }
    return GoldenCase.model_validate({**base, **fields})


def _claim(status: str, claim: str = "Pro costs 1490 EUR") -> ClaimCheck:
    evidence = "acme-p-2" if status == "verified" else None
    return ClaimCheck(claim=claim, kind="price", status=status, evidence=evidence, reason="r")  # type: ignore[arg-type]


def _outcome(
    pack: ContextPack,
    body: str = "Insight Pro costs 1490.00 EUR.",
    claims: tuple[ClaimCheck, ...] = (),
    route: str = "approval",
    cited: tuple[str, ...] = (),
    subject: str = "Your quote",
) -> HarmonizeOutcome:
    return HarmonizeOutcome(
        email=HarmonizedEmail(subject=subject, body=body, rationale="r", cited_nodes=cited),
        decision=Decision(route=route, reasons=("x",)),  # type: ignore[arg-type]
        trace_id="acme-001",
        steps=(),
        claim_checks=claims,
        context=pack,
    )


def test_a_clean_email_holding_every_required_string_scores_perfectly(pack: ContextPack) -> None:
    score = fact_accuracy(
        _case(must_contain=["1490"]), _outcome(pack, claims=(_claim("verified"),))
    )
    assert (score.false_claims, score.missing, score.passed) == (0, (), True)


def test_false_claims_are_counted_and_unknown_ones_are_not(pack: ContextPack) -> None:
    claims = (
        _claim("false"),
        _claim("false", "Ultra"),
        _claim("unknown", "SSO"),
        _claim("verified"),
    )
    score = fact_accuracy(_case(), _outcome(pack, claims=claims))
    assert score.false_claims == 2 and not score.passed


def test_a_missing_required_string_fails_the_case_and_is_named(pack: ContextPack) -> None:
    score = fact_accuracy(
        _case(must_contain=["1490", "Insight Pro", "EUR"]), _outcome(pack, body="Pro costs 990.")
    )
    assert score.missing == ("1490", "Insight Pro", "EUR") and not score.passed


def test_required_strings_are_matched_without_regard_to_case_and_in_the_subject(
    pack: ContextPack,
) -> None:
    outcome = _outcome(pack, body="costs 1490", subject="INSIGHT PRO")
    assert fact_accuracy(_case(must_contain=["insight pro", "1490"]), outcome).passed


def test_forbidden_patterns_are_reported_in_order_and_only_when_they_match(
    pack: ContextPack,
) -> None:
    outcome = _outcome(pack, body="We offer 50% off, and unlimited training.")
    case = _case(forbidden=[r"(?i)unlimited\s+training", r"\d+% off", r"never matches"])
    assert case_forbidden_hits(case, outcome) == (r"(?i)unlimited\s+training", r"\d+% off")
    assert forbidden_hits("plain text", [r"\d+% off"]) == ()


def test_routing_compares_the_decided_route_with_the_expected_one(pack: ContextPack) -> None:
    assert routing_ok(_case(expected_route="approval"), _outcome(pack, route="approval"))
    assert not routing_ok(_case(expected_route="approval"), _outcome(pack, route="blocked"))


def test_traceability_accepts_existing_nodes_and_rules_that_apply(pack: ContextPack) -> None:
    rules = load_rules(ACME)
    applicable = pack.rules[0].id
    known = {r.id for r in rules} | {"acme-p-2"}
    outcome = _outcome(pack, cited=(applicable, "acme-p-2"))
    score = traceability(_case(), outcome, rules, known)
    assert score.passed and score.cited == (applicable, "acme-p-2")


def test_traceability_names_an_unknown_node_and_a_rule_that_does_not_apply(
    pack: ContextPack,
) -> None:
    rules = load_rules(ACME)
    in_pack = {r.id for r in pack.rules}
    foreign = next(r.id for r in rules if r.status == "approved" and r.id not in in_pack)
    outcome = _outcome(pack, cited=("acme-r-999", foreign))
    score = traceability(_case(), outcome, rules, {r.id for r in rules})
    assert score.unknown == ("acme-r-999",)
    assert score.inapplicable == (foreign,)
    assert not score.passed


def test_an_email_that_cites_nothing_has_nothing_untraceable(pack: ContextPack) -> None:
    assert traceability(_case(), _outcome(pack), (), set()).passed


def _questions() -> list[RetrievalQuestion]:
    return [
        RetrievalQuestion(
            question=f"q{i}", expected_doc_id="d-1", expected_quote=f"quote number {i}"
        )
        for i in range(4)
    ]


def _hit(doc: str, text: str) -> SearchHit:
    return SearchHit(chunk_id=f"{doc}-c", doc_id=doc, text=text, score=1.0)


def test_recall_counts_questions_whose_top_five_hold_the_expected_passage() -> None:
    answers = {
        "q0": [_hit("d-1", "a quote  number 0 inside")],  # extra spaces are ignored
        "q1": [_hit("d-2", "quote number 1")],  # right text, wrong interview
        "q2": [_hit("d-9", "x")] * 5 + [_hit("d-1", "quote number 2")],  # sixth place
        "q3": [_hit("d-1", "quote number 3")],
    }
    score = retrieval_recall(_questions(), lambda q: answers[q])
    assert (score.found, score.total, score.k) == (2, 4, 5)
    assert score.missed == ("q1", "q2") and score.recall == 0.5


def test_recall_of_no_question_is_zero_and_says_so() -> None:
    score = retrieval_recall([], lambda q: [])
    assert (score.found, score.total, score.recall) == (0, 0, 0.0)
