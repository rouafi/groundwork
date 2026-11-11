import pytest
from pydantic import ValidationError

from groundwork.core.domain.pack import PackConfig

VALID = {"crm": "fixture", "messaging": "console", "vector_store": "lancedb", "model": "replay"}


def test_valid_config_is_accepted() -> None:
    assert PackConfig.model_validate(VALID).crm == "fixture"


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PackConfig.model_validate({**VALID, "script": "rm -rf /"})


def test_missing_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PackConfig.model_validate({k: v for k, v in VALID.items() if k != "crm"})
