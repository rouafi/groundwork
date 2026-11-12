import itertools

import pytest

from groundwork.core.domain.claims import ClaimCheck
from groundwork.core.domain.harmonize import HarmonizedEmail
from groundwork.core.domain.policy import ForbiddenPatterns, Policies
from groundwork.core.services.policy import decide

POLICIES = Policies(
    forbidden_patterns=ForbiddenPatterns(
        internal=(r"(?i)password\s*[:=]\s*\S+",),
        external=(r"(?i)\b\d{1,3}\s?%\s?off\b",),
    )
)


def _email(body: str = "Insight Pro costs 1490.00 EUR.") -> HarmonizedEmail:
    return HarmonizedEmail(subject="Your question", body=body, rationale="r")


def _claim(status: str, claim: str = "Pro costs 1490 EUR") -> ClaimCheck:
    evidence = "acme-p-2" if status == "verified" else None
    return ClaimCheck(
        claim=claim,
        kind="price",
        status=status,
        evidence=evidence,
        reason="the catalog says so",  # type: ignore[arg-type]
    )


def test_a_valid_internal_email_auto_sends() -> None:
    decision = decide(_email(), [_claim("verified")], "internal", POLICIES)
    assert decision.route == "auto_send"
    assert decision.reasons


def test_a_valid_external_email_goes_to_approval() -> None:
    decision = decide(_email(), [_claim("verified")], "external", POLICIES)
    assert decision.route == "approval"
    assert "never sent automatically" in decision.reasons[0]


def test_an_external_email_with_a_wrong_price_is_blocked_and_says_why() -> None:
    decision = decide(_email(), [_claim("false", "Pro costs 990 EUR")], "external", POLICIES)
    assert decision.route == "blocked"
    assert "Pro costs 990 EUR" in decision.reasons[0]
    assert "the catalog says so" in decision.reasons[0]


def test_an_email_matching_a_forbidden_pattern_is_blocked_and_names_it() -> None:
    decision = decide(_email("We can do 50% off today."), [], "external", POLICIES)
    assert decision.route == "blocked"
    assert "50% off" in decision.reasons[0]
    assert "external email" in decision.reasons[0]


def test_the_subject_is_checked_too() -> None:
    email = HarmonizedEmail(subject="50% off", body="Hello.", rationale="r")
    assert decide(email, [], "external", POLICIES).route == "blocked"


def test_a_pattern_of_one_channel_does_not_block_the_other() -> None:
    assert decide(_email("We can do 50% off."), [], "internal", POLICIES).route == "auto_send"
    assert decide(_email("password: hunter2"), [], "external", POLICIES).route == "approval"
    assert decide(_email("password: hunter2"), [], "internal", POLICIES).route == "blocked"


def test_every_blocking_reason_is_listed() -> None:
    decision = decide(_email("50% off"), [_claim("false")], "external", POLICIES)
    assert decision.route == "blocked"
    assert len(decision.reasons) == 2


def test_an_unknown_claim_goes_to_a_human_even_on_an_internal_email() -> None:
    decision = decide(_email(), [_claim("unknown", "We include SSO")], "internal", POLICIES)
    assert decision.route == "approval"
    assert "We include SSO" in decision.reasons[0]


def test_an_external_approval_lists_its_unknown_claims() -> None:
    decision = decide(_email(), [_claim("unknown", "We include SSO")], "external", POLICIES)
    assert decision.route == "approval"
    assert any("We include SSO" in r for r in decision.reasons)


def test_internal_auto_send_can_be_turned_off() -> None:
    policies = POLICIES.model_copy(update={"auto_send_internal": False})
    decision = decide(_email(), [_claim("verified")], "internal", policies)
    assert decision.route == "approval"
    assert "auto-send is off" in decision.reasons[0]


def test_an_external_email_never_auto_sends_whatever_the_inputs() -> None:
    bodies = ["Plain.", "50% off", "password: x"]
    statuses = [(), ("verified",), ("unknown",), ("false",), ("verified", "unknown")]
    for body, claims, internal_on in itertools.product(bodies, statuses, [True, False]):
        policies = POLICIES.model_copy(update={"auto_send_internal": internal_on})
        decision = decide(_email(body), [_claim(s) for s in claims], "external", policies)
        assert decision.route != "auto_send", (body, claims, internal_on)


def test_a_false_claim_always_blocks_whatever_the_channel_and_policies() -> None:
    for channel, internal_on in itertools.product(["internal", "external"], [True, False]):
        policies = POLICIES.model_copy(update={"auto_send_internal": internal_on})
        decision = decide(_email(), [_claim("verified"), _claim("false")], channel, policies)  # type: ignore[arg-type]
        assert decision.route == "blocked"


@pytest.mark.parametrize("channel", ["internal", "external"])
def test_an_email_with_no_claim_and_no_pattern_is_not_blocked(channel: str) -> None:
    assert decide(_email(), [], channel, POLICIES).route != "blocked"  # type: ignore[arg-type]
