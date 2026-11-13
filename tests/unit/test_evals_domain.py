import pytest
from pydantic import ValidationError

from groundwork.core.domain.evals import GoldenCase, Thresholds

CASE = {
    "id": "acme-001",
    "contact_id": "acme-c-1",
    "channel": "external",
    "draft": "Hi, Pro is 990 EUR.",
    "must_contain": ["1490"],
    "forbidden": [r"(?i)\d+\s?%\s?off"],
    "expected_route": "approval",
    "tags": ["wrong-price"],
}


def test_a_golden_case_holds_what_a_good_result_looks_like() -> None:
    case = GoldenCase.model_validate(CASE)
    assert case.must_contain == ("1490",) and case.expected_route == "approval"
    assert case.tags == ("wrong-price",)


def test_a_case_needs_only_its_request_and_the_expected_route() -> None:
    minimal = {k: CASE[k] for k in ("id", "contact_id", "channel", "draft", "expected_route")}
    case = GoldenCase.model_validate(minimal)
    assert case.must_contain == () and case.forbidden == () and case.tags == ()


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        ({"forbidden": ["(unclosed"]}, "invalid regular expression"),
        ({"channel": "any"}, "channel"),
        ({"expected_route": "send"}, "expected_route"),
        ({"id": "../x"}, "id"),
        ({"draft": ""}, "draft"),
        ({"extra": 1}, "extra"),
        ({"channel": "external", "expected_route": "auto_send"}, "never do"),
    ],
)
def test_an_invalid_case_is_rejected_for_the_right_reason(
    change: dict[str, object], needle: str
) -> None:
    with pytest.raises(ValidationError, match=needle):
        GoldenCase.model_validate({**CASE, **change})


def test_an_internal_case_may_expect_auto_send() -> None:
    case = GoldenCase.model_validate({**CASE, "channel": "internal", "expected_route": "auto_send"})
    assert case.expected_route == "auto_send"


def test_the_thresholds_default_to_the_ones_of_the_prd() -> None:
    thresholds = Thresholds()
    assert thresholds.model_dump() == {
        "fact_false_claims": 0,
        "rule_violations": 0,
        "tone_mean_min": 4.0,
        "routing_accuracy_min": 1.0,
        "traceability_min": 1.0,
        "retrieval_recall_at_5_min": 0.8,
        "judge_agreement_min": 0.8,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"tone_mean_min": 0.5},
        {"tone_mean_min": 5.5},
        {"routing_accuracy_min": 1.2},
        {"fact_false_claims": -1},
        {"surprise": 1},
    ],
)
def test_thresholds_outside_their_range_or_unknown_are_rejected(change: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        Thresholds.model_validate(change)
