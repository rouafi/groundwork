import pytest
from pydantic import ValidationError

from groundwork.core.domain.pack import PackConfig

VALID = {
    "crm": "fixture",
    "messaging": "console",
    "vector_store": "lancedb",
    "model": "replay",
    "domain": "comms",
}


def test_valid_config_is_accepted() -> None:
    config = PackConfig.model_validate(VALID)
    assert (config.crm, config.domain) == ("fixture", "comms")


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PackConfig.model_validate({**VALID, "script": "rm -rf /"})


@pytest.mark.parametrize("key", ["crm", "domain"])
def test_missing_key_is_rejected(key: str) -> None:
    with pytest.raises(ValidationError):
        PackConfig.model_validate({k: v for k, v in VALID.items() if k != key})


@pytest.mark.parametrize("domain", ["../secrets", "Comms", "comms/x", ""])
def test_domain_must_be_a_folder_slug(domain: str) -> None:
    with pytest.raises(ValidationError):
        PackConfig.model_validate({**VALID, "domain": domain})
