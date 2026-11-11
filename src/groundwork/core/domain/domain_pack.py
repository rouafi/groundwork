"""Domain pack vocabulary: the values a client pack may use for this business domain."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    duplicates = sorted({v for v in values if values.count(v) > 1})
    if duplicates:
        raise ValueError(f"duplicate values: {', '.join(duplicates)}")
    return values


Vocabulary = Annotated[tuple[str, ...], Field(min_length=1), AfterValidator(_unique)]


class DomainDefaults(BaseModel):
    """Defaults a client pack inherits unless it overrides them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tone: str = Field(min_length=1)


class DomainPack(BaseModel):
    """Schema of `domains/<domain>/domain.yaml`. Data only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    segments: Vocabulary
    personas: Vocabulary
    channels: Vocabulary
    defaults: DomainDefaults
