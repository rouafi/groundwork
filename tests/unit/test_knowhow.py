from typing import Any

import pytest
from pydantic import ValidationError

from groundwork.core.domain.knowhow import (
    Conflict,
    ExtractionReport,
    Interview,
    Provenance,
    Rule,
    Scope,
    Usage,
)

PROVENANCE: dict[str, Any] = {
    "interview_id": "acme-i-1",
    "quote": "We never put a discount in writing.",
    "start": 10,
    "end": 45,
}
RULE: dict[str, Any] = {
    "id": "acme-r-001",
    "kind": "claim",
    "statement": "Never state a discount in an external email.",
    "scope": {"channel": "external"},
    "provenance": [PROVENANCE],
}


def test_rule_defaults_to_proposed_and_is_frozen() -> None:
    rule = Rule.model_validate(RULE)
    assert rule.status == "proposed"
    assert rule.provenance[0].quote == PROVENANCE["quote"]
    with pytest.raises(ValidationError):
        rule.status = "approved"  # type: ignore[misc]


def test_rule_rejects_unknown_fields_and_bad_ids() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Rule.model_validate({**RULE, "priority": 1})
    with pytest.raises(ValidationError, match="id"):
        Rule.model_validate({**RULE, "id": "rule-1"})


def test_rule_needs_provenance() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        Rule.model_validate({**RULE, "provenance": []})


def test_claim_text_only_on_claim_rules() -> None:
    assert Rule.model_validate({**RULE, "claim_text": "SSO included"}).claim_text
    with pytest.raises(ValidationError, match="claim_text is only allowed"):
        Rule.model_validate({**RULE, "kind": "tone", "claim_text": "SSO included"})


def test_provenance_span_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="end"):
        Provenance.model_validate({**PROVENANCE, "end": 10})
    with pytest.raises(ValidationError, match="start"):
        Provenance.model_validate({**PROVENANCE, "start": -1})


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (Scope(), True),
        (Scope(channel="external"), True),
        (Scope(channel="internal"), False),
        (Scope(segments=("smb",)), True),
        (Scope(segments=("enterprise",)), False),
        (Scope(personas=("end-user",)), False),
    ],
)
def test_scope_applies_to(scope: Scope, expected: bool) -> None:
    assert scope.applies_to("external", "smb", "economic-buyer") is expected


def test_scope_specificity_counts_constrained_dimensions() -> None:
    assert Scope().specificity == 0
    assert Scope(channel="external", segments=("smb",)).specificity == 2
    assert Scope(channel="internal", segments=("smb",), personas=("end-user",)).specificity == 3


def test_scope_rejects_unknown_channel() -> None:
    with pytest.raises(ValidationError):
        Scope.model_validate({"channel": "sms"})


def test_interview_needs_text() -> None:
    with pytest.raises(ValidationError):
        Interview(id="acme-i-1", role="head of sales", text="")


def test_usage_adds_up() -> None:
    total = Usage(input_tokens=10, output_tokens=2) + Usage(input_tokens=5, output_tokens=1)
    assert total == Usage(input_tokens=15, output_tokens=3)


def test_conflict_needs_two_rules() -> None:
    with pytest.raises(ValidationError):
        Conflict(rule_ids=("acme-r-001",), reason="disagree")


def test_report_round_trips_through_json() -> None:
    report = ExtractionReport(pack="acme", rules=(Rule.model_validate(RULE),))
    assert ExtractionReport.model_validate_json(report.model_dump_json()) == report
