from typing import Any

import pytest

from groundwork.core.domain.domain_pack import DomainDefaults, DomainPack
from groundwork.core.domain.knowhow import Dropped, Interview, Rule
from groundwork.core.ports.model import CitedStatement, Quote
from groundwork.core.services.grounding import TypedRule, check_candidate, locate, normalize

LSQ, RSQ, DASH, NBSP = chr(0x2018), chr(0x2019), chr(0x2014), chr(0x00A0)
TEXT = f"Hi.  We never put a discount in writing.\nKeep it {LSQ}short{RSQ} {DASH} always."
INTERVIEW = Interview(id="acme-i-1", role="head of sales", text=TEXT)
DOMAIN = DomainPack(
    segments=("smb", "mid-market", "enterprise"),
    personas=("economic-buyer", "technical-evaluator", "end-user"),
    channels=("internal", "external"),
    defaults=DomainDefaults(tone="formal"),
)
PRODUCTS = {"acme-p-1"}


def _quote(text: str) -> Quote:
    start = TEXT.index(text)
    return Quote(text=text, start=start, end=start + len(text))


def _typed(**overrides: Any) -> TypedRule:
    fields: dict[str, Any] = {
        "index": 0,
        "kind": "claim",
        "statement": "Never state a discount in writing.",
        "channel": "external",
        "segments": [],
        "personas": [],
        "product_ids": [],
        "claim_text": None,
    }
    return TypedRule(**(fields | overrides))


def _check(statement: CitedStatement, typed: TypedRule) -> Rule | Dropped:
    return check_candidate(INTERVIEW, statement, typed, DOMAIN, PRODUCTS)


DISCOUNT = CitedStatement(
    text="No discount", quotes=(_quote("We never put a discount in writing."),)
)


def test_normalize_collapses_whitespace_and_typography() -> None:
    assert (
        normalize(f"  Keep it {LSQ}short{RSQ} {DASH}\n always.{NBSP}")
        == "Keep it 'short' - always."
    )


def test_locate_keeps_the_api_span_when_it_matches() -> None:
    provenance = locate(TEXT, _quote("We never put a discount in writing."))
    assert provenance is not None
    assert TEXT[provenance.start : provenance.end] == provenance.quote


def test_locate_accepts_typographic_differences_on_the_same_span() -> None:
    span = _quote(f"Keep it {LSQ}short{RSQ} {DASH} always.")
    ascii_quote = Quote(text="Keep it 'short' - always.", start=span.start, end=span.end)
    provenance = locate(TEXT, ascii_quote)
    assert provenance is not None and provenance.quote == span.text


def test_locate_trims_whitespace_and_finds_a_misplaced_quote() -> None:
    quote = Quote(text=" We never put a discount in writing. ", start=0, end=3)
    provenance = locate(TEXT, quote)
    assert provenance is not None
    assert provenance.quote == "We never put a discount in writing."


@pytest.mark.parametrize("text", ["We always give 50% off.", "   "])
def test_locate_rejects_text_that_is_not_in_the_transcript(text: str) -> None:
    assert locate(TEXT, Quote(text=text, start=0, end=len(text))) is None


def test_a_grounded_candidate_becomes_a_proposed_rule() -> None:
    rule = _check(DISCOUNT, _typed())
    assert isinstance(rule, Rule)
    assert rule.status == "proposed"
    assert rule.provenance[0].interview_id == "acme-i-1"
    assert rule.scope.channel == "external"


@pytest.mark.parametrize(
    ("statement", "typed", "reason"),
    [
        (CitedStatement(text="x", quotes=()), _typed(), "no citation"),
        (
            CitedStatement(text="x", quotes=(Quote(text="Invented.", start=0, end=9),)),
            _typed(),
            "quote not found verbatim",
        ),
        (DISCOUNT, _typed(segments=["startup"]), "segment 'startup' not in the domain"),
        (DISCOUNT, _typed(personas=["ceo"]), "persona 'ceo' not in the domain"),
        (DISCOUNT, _typed(product_ids=["acme-p-9"]), "unknown product acme-p-9"),
        (DISCOUNT, _typed(statement="  "), "empty statement"),
        (DISCOUNT, _typed(kind="tone", claim_text="SSO"), "claim_text on a non-claim rule"),
    ],
)
def test_candidates_are_dropped_with_a_reason(
    statement: CitedStatement, typed: TypedRule, reason: str
) -> None:
    dropped = _check(statement, typed)
    assert isinstance(dropped, Dropped)
    assert reason in dropped.reason
    assert dropped.interview_id == "acme-i-1"


def test_channel_outside_the_domain_is_dropped() -> None:
    narrow = DOMAIN.model_copy(update={"channels": ("external",)})
    result = check_candidate(INTERVIEW, DISCOUNT, _typed(channel="internal"), narrow, PRODUCTS)
    assert isinstance(result, Dropped)
    assert "channel 'internal'" in result.reason
