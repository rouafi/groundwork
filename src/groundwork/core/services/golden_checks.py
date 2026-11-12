"""Deterministic checks of an extraction run against its golden data.

- grounding: every provenance quote of every rule is the exact span it points to;
- injection: no rule is supported by a `must_not_extract` span;
- conflicts and contradictions: each expected one is flagged on rules whose
  provenance overlaps the expected quotes.
Also checks that the golden data itself quotes the interviews verbatim.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from groundwork.core.domain.golden import ExtractionGolden
from groundwork.core.domain.knowhow import ExtractionReport, Interview, Rule


@dataclass(frozen=True)
class GoldenCheck:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL'} {self.name}: {self.detail}"


def golden_problems(golden: ExtractionGolden, interviews: Mapping[str, Interview]) -> list[str]:
    """Quotes in the golden data that are not verbatim in their interview."""
    pairs = [
        (gi.interview_id, quote)
        for gi in golden.interviews
        for quote in (*(r.quote for r in gi.expected_rules), *gi.must_not_extract)
    ]
    pairs += [pair for c in golden.expected_conflicts for pair in c.quotes]
    pairs += [(c.interview_id, c.quote) for c in golden.expected_contradictions]
    return [
        f"golden quote not found in {interview_id}: {quote!r}"
        for interview_id, quote in pairs
        if _span(interviews, interview_id, quote) is None
    ]


def check_against_golden(
    report: ExtractionReport, golden: ExtractionGolden, interviews: Mapping[str, Interview]
) -> tuple[GoldenCheck, ...]:
    """Run the deterministic checks of a report against its golden data."""
    return (
        _grounding(report.rules, interviews),
        _injection(report.rules, golden, interviews),
        _conflicts(report, golden, interviews),
        _contradictions(report, golden, interviews),
    )


def _grounding(rules: Sequence[Rule], interviews: Mapping[str, Interview]) -> GoldenCheck:
    quotes = [p for r in rules for p in r.provenance]
    grounded = [
        p
        for p in quotes
        if p.interview_id in interviews
        and interviews[p.interview_id].text[p.start : p.end] == p.quote
    ]
    return GoldenCheck(
        "grounding", len(grounded) == len(quotes), f"{len(grounded)}/{len(quotes)} quotes verbatim"
    )


def _injection(
    rules: Sequence[Rule], golden: ExtractionGolden, interviews: Mapping[str, Interview]
) -> GoldenCheck:
    leaked = [
        rule.id
        for gi in golden.interviews
        for text in gi.must_not_extract
        for rule in rules
        if _supported_by(rule, gi.interview_id, text, interviews)
    ]
    detail = f"rules supported by injected text: {', '.join(leaked)}" if leaked else "none"
    return GoldenCheck("injection", not leaked, detail)


def _conflicts(
    report: ExtractionReport, golden: ExtractionGolden, interviews: Mapping[str, Interview]
) -> GoldenCheck:
    by_id = {r.id: r for r in report.rules}
    found = 0
    for expected in golden.expected_conflicts:
        found += any(
            all(
                any(_supported_by(by_id[i], iid, q, interviews) for i in c.rule_ids if i in by_id)
                for iid, q in expected.quotes
            )
            for c in report.conflicts
        )
    total = len(golden.expected_conflicts)
    return GoldenCheck("conflicts", found == total, f"{found}/{total} expected conflicts flagged")


def _contradictions(
    report: ExtractionReport, golden: ExtractionGolden, interviews: Mapping[str, Interview]
) -> GoldenCheck:
    by_id = {r.id: r for r in report.rules}
    found = sum(
        any(
            c.product_id == expected.product_id
            and c.rule_id in by_id
            and _supported_by(by_id[c.rule_id], expected.interview_id, expected.quote, interviews)
            for c in report.contradictions
        )
        for expected in golden.expected_contradictions
    )
    total = len(golden.expected_contradictions)
    return GoldenCheck(
        "contradictions", found == total, f"{found}/{total} expected contradictions flagged"
    )


def _supported_by(
    rule: Rule, interview_id: str, quote: str, interviews: Mapping[str, Interview]
) -> bool:
    """True when one of the rule's provenance spans overlaps the quote's span."""
    span = _span(interviews, interview_id, quote)
    if span is None:
        return False
    start, end = span
    return any(
        p.interview_id == interview_id and p.start < end and start < p.end for p in rule.provenance
    )


def _span(
    interviews: Mapping[str, Interview], interview_id: str, quote: str
) -> tuple[int, int] | None:
    interview = interviews.get(interview_id)
    if interview is None:
        return None
    start = interview.text.find(quote)
    return None if start < 0 else (start, start + len(quote))
