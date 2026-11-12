import pytest
from pydantic import ValidationError

from groundwork.core.domain.claims import ClaimCheck, ExtractedClaim


def test_a_verified_claim_names_its_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        ClaimCheck(claim="Pro costs 49 EUR.", kind="price", status="verified", reason="ok")


def test_a_claim_check_is_frozen_and_rejects_unknown_fields() -> None:
    check = ClaimCheck(
        claim="Pro costs 49 EUR.",
        kind="price",
        status="verified",
        evidence="acme-p-pro",
        reason="49 EUR is the catalog price",
    )
    with pytest.raises(ValidationError):
        check.status = "false"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ClaimCheck.model_validate({**check.model_dump(), "extra": 1})


@pytest.mark.parametrize("kind", ["price", "product_name", "feature", "other"])
def test_extracted_claims_accept_every_kind(kind: str) -> None:
    assert ExtractedClaim(text="x", kind=kind).product_id is None  # type: ignore[arg-type]


def test_an_unknown_kind_or_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractedClaim(text="x", kind="discount")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ClaimCheck(claim="x", kind="other", status="maybe", reason="r")  # type: ignore[arg-type]
