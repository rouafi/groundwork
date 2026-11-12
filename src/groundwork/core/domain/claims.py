"""Claims in a draft and their check against the facts.

A claim is one statement a draft makes about the client's offer: a price, a
product name, a feature. Facts decide; when they cannot, the status is `unknown`
and a human reads it. `false` is reserved for a statement the facts contradict.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimKind = Literal["price", "product_name", "feature", "other"]
ClaimStatus = Literal["verified", "false", "unknown"]


class _Claim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExtractedClaim(_Claim):
    """One atomic claim found in a text by the model, before any check.

    `product_id` is the catalog id the claim is about, if any; `value` is the
    amount and currency of a price ("49 EUR") or the product name as written.
    """

    text: str = Field(min_length=1)
    kind: ClaimKind
    product_id: str | None = None
    value: str | None = None


class ClaimCheck(_Claim):
    """The verdict on one claim. `evidence` is the id of the fact it was checked against."""

    claim: str = Field(min_length=1)
    kind: ClaimKind
    status: ClaimStatus
    evidence: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _verified_needs_evidence(self) -> Self:
        if self.status == "verified" and self.evidence is None:
            raise ValueError("a verified claim must name its evidence")
        return self
