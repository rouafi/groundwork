"""Client pack configuration: which adapter each port uses."""

from pydantic import BaseModel, ConfigDict


class PackConfig(BaseModel):
    """Schema of `client_packs/<client>/config.yaml`. Data only, validated in CI."""

    model_config = ConfigDict(extra="forbid")

    crm: str
    messaging: str
    vector_store: str
    model: str
