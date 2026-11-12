"""Deterministic checks on extracted candidates. No model here: this is the guard.

A candidate becomes a rule only if every quote it cites is found verbatim in the
transcript (after normalizing whitespace and typographic punctuation), its scope
uses the domain vocabulary, its products exist in the CRM, and it says something.
"""

import re
from collections.abc import Collection

from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.knowhow import (
    Channel,
    Dropped,
    Interview,
    Provenance,
    Rule,
    RuleKind,
    Scope,
)
from groundwork.core.ports.model import CitedStatement, Quote

_TYPOGRAPHIC = str.maketrans(
    {
        chr(0x2018): "'",  # left single quotation mark
        chr(0x2019): "'",  # right single quotation mark
        chr(0x201C): '"',  # left double quotation mark
        chr(0x201D): '"',  # right double quotation mark
        chr(0x2013): "-",  # en dash
        chr(0x2014): "-",  # em dash
        chr(0x00A0): " ",  # no-break space
    }
)
PLACEHOLDER_ID = "pending-r-000"


class TypedRule(BaseModel):
    """What the typing stage returns for one cited statement, by its index."""

    model_config = ConfigDict(extra="forbid")

    index: int
    kind: RuleKind
    statement: str
    channel: Channel
    segments: list[str]
    personas: list[str]
    product_ids: list[str]
    claim_text: str | None


def normalize(text: str) -> str:
    """Collapse whitespace and map typographic quotes and dashes to ASCII."""
    return re.sub(r"\s+", " ", text.translate(_TYPOGRAPHIC)).strip()


def locate(transcript: str, quote: Quote) -> Provenance | None:
    """Where the quote is in the transcript, or None if it is not there verbatim."""
    if not normalize(quote.text):
        return None
    span = transcript[quote.start : quote.end] if 0 <= quote.start < quote.end else ""
    if span and normalize(span) == normalize(quote.text):
        start, end = quote.start, quote.end
    else:
        start = transcript.find(quote.text.strip())
        if start < 0 or not quote.text.strip():
            return None
        end = start + len(quote.text.strip())
    stripped = transcript[start:end]
    start += len(stripped) - len(stripped.lstrip())
    end -= len(stripped) - len(stripped.rstrip())
    return Provenance(interview_id="pending", quote=transcript[start:end], start=start, end=end)


def check_candidate(
    interview: Interview,
    statement: CitedStatement,
    typed: TypedRule,
    domain: DomainPack,
    product_ids: Collection[str],
) -> Rule | Dropped:
    """Turn one typed statement into a proposed rule, or say why it is dropped."""
    reason = _scope_problem(typed, domain) or _product_problem(typed, product_ids)
    if not typed.statement.strip():
        reason = "empty statement"
    if not statement.quotes:
        reason = "no citation"
    provenance = [locate(interview.text, quote) for quote in statement.quotes]
    if any(p is None for p in provenance):
        reason = reason or "quote not found verbatim in the transcript"
    if typed.claim_text is not None and typed.kind != "claim":
        reason = reason or "claim_text on a non-claim rule"
    if reason:
        return Dropped(interview_id=interview.id, statement=statement.text, reason=reason)
    return Rule(
        id=PLACEHOLDER_ID,
        kind=typed.kind,
        statement=typed.statement.strip(),
        scope=Scope(
            channel=typed.channel,
            segments=tuple(typed.segments),
            personas=tuple(typed.personas),
        ),
        provenance=tuple(
            p.model_copy(update={"interview_id": interview.id}) for p in provenance if p
        ),
        product_ids=tuple(typed.product_ids),
        claim_text=typed.claim_text or None,
    )


def _scope_problem(typed: TypedRule, domain: DomainPack) -> str | None:
    if typed.channel != "any" and typed.channel not in domain.channels:
        return f"channel {typed.channel!r} not in the domain vocabulary"
    for field, values, allowed in (
        ("segment", typed.segments, domain.segments),
        ("persona", typed.personas, domain.personas),
    ):
        unknown = [v for v in values if v not in allowed]
        if unknown:
            return f"{field} {unknown[0]!r} not in the domain vocabulary"
    return None


def _product_problem(typed: TypedRule, product_ids: Collection[str]) -> str | None:
    unknown = [p for p in typed.product_ids if p not in product_ids]
    return f"unknown product {unknown[0]}" if unknown else None
