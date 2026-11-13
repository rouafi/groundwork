"""The discovery document of a client: what the use case is, for whom, and how success is measured.

It is the artifact of day 1 of the playbook (docs/playbook.md). A sponsor signs it off, and
only then does the rest of the onboarding start. Signing off is a human action: this type
checks that it was recorded consistently, it never decides it.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1)]
ClientName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
Channel = Literal["internal", "external"]
DiscoveryStatus = Literal["draft", "signed_off"]


class _Discovery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class System(_Discovery):
    """A system the use case reads from or writes to, and the part it plays."""

    name: Text
    role: Text


class SuccessMetric(_Discovery):
    """How the sponsor will know it worked: the measure, where it stands, where it should be."""

    name: Text
    baseline: Text
    target: Text


class DiscoveryDoc(_Discovery):
    """`client_packs/<client>/discovery.yaml`. Valid means complete, not approved."""

    client: ClientName
    sponsor: Text
    use_case: Text
    users: Annotated[tuple[Text, ...], Field(min_length=1)]
    channels: Annotated[tuple[Channel, ...], Field(min_length=1)]
    systems: Annotated[tuple[System, ...], Field(min_length=1)]
    success_metric: SuccessMetric
    risks: Annotated[tuple[Text, ...], Field(min_length=1)]
    status: DiscoveryStatus = "draft"
    signed_off_by: str | None = None

    @field_validator("channels")
    @classmethod
    def _distinct_channels(cls, channels: tuple[Channel, ...]) -> tuple[Channel, ...]:
        if len(set(channels)) != len(channels):
            raise ValueError("each channel appears once")
        return channels

    @model_validator(mode="after")
    def _signature_matches_status(self) -> Self:
        signed = bool(self.signed_off_by and self.signed_off_by.strip())
        if self.status == "signed_off" and not signed:
            raise ValueError("signed_off_by: a signed-off discovery names who signed it off")
        if self.status == "draft" and self.signed_off_by:
            raise ValueError("signed_off_by is set but status is still draft")
        return self

    @property
    def is_signed_off(self) -> bool:
        return self.status == "signed_off"
