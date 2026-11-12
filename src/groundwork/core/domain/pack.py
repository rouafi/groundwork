"""Client pack configuration: which adapter each port uses, and which domain the pack uses."""

from pydantic import BaseModel, ConfigDict, Field


class PackConfig(BaseModel):
    """Schema of `client_packs/<client>/config.yaml`. Data only, validated in CI."""

    model_config = ConfigDict(extra="forbid")

    crm: str
    messaging: str
    vector_store: str
    model: str
    embedding: str = "replay"
    # A folder name under domains/: a slug, so it can never escape that folder.
    domain: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
