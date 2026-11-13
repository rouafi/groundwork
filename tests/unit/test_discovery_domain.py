from typing import Any

import pytest
from pydantic import ValidationError

from groundwork.core.domain.discovery import DiscoveryDoc

VALID: dict[str, Any] = {
    "client": "gamma",
    "sponsor": "Head of customer success",
    "use_case": "Harmonize customer emails so every team states the same prices and promises.",
    "users": ["account managers", "customer success"],
    "channels": ["internal", "external"],
    "systems": [{"name": "HubSpot", "role": "contacts, deals and products"}],
    "success_metric": {
        "name": "emails corrected by a manager",
        "baseline": "about 30% of external emails",
        "target": "under 10%",
    },
    "risks": ["a wrong price reaches a customer"],
}


def _doc(**changes: Any) -> DiscoveryDoc:
    return DiscoveryDoc.model_validate({**VALID, **changes})


def test_a_complete_discovery_is_a_valid_draft() -> None:
    doc = _doc()
    assert doc.status == "draft" and not doc.is_signed_off
    assert doc.signed_off_by is None


def test_a_signed_off_discovery_names_who_signed() -> None:
    doc = _doc(status="signed_off", signed_off_by="Ana Silva, sponsor")
    assert doc.is_signed_off


@pytest.mark.parametrize("signer", [None, "", "   "])
def test_signed_off_without_a_name_is_refused(signer: str | None) -> None:
    with pytest.raises(ValidationError, match="names who signed"):
        _doc(status="signed_off", signed_off_by=signer)


def test_a_signature_on_a_draft_is_refused() -> None:
    with pytest.raises(ValidationError, match="still draft"):
        _doc(signed_off_by="Ana Silva")


@pytest.mark.parametrize(
    "field",
    ["client", "sponsor", "use_case", "users", "channels", "systems", "success_metric", "risks"],
)
def test_every_required_field_is_named_when_missing(field: str) -> None:
    data = {k: v for k, v in VALID.items() if k != field}
    with pytest.raises(ValidationError) as error:
        DiscoveryDoc.model_validate(data)
    assert [e["loc"] for e in error.value.errors()] == [(field,)]


@pytest.mark.parametrize(
    ("change", "location"),
    [
        ({"sponsor": ""}, ("sponsor",)),
        ({"users": []}, ("users",)),
        ({"risks": [""]}, ("risks", 0)),
        ({"systems": [{"name": "HubSpot", "role": ""}]}, ("systems", 0, "role")),
        (
            {"success_metric": {"name": "x", "baseline": "", "target": "y"}},
            ("success_metric", "baseline"),
        ),
        ({"channels": []}, ("channels",)),
    ],
)
def test_an_empty_value_is_refused_at_the_field_that_is_empty(
    change: dict[str, Any], location: tuple[Any, ...]
) -> None:
    with pytest.raises(ValidationError) as error:
        _doc(**change)
    assert location in [e["loc"] for e in error.value.errors()]


def test_a_channel_must_be_internal_or_external_and_appear_once() -> None:
    with pytest.raises(ValidationError):
        _doc(channels=["any"])
    with pytest.raises(ValidationError, match="appears once"):
        _doc(channels=["internal", "internal"])


@pytest.mark.parametrize("client", ["Gamma", "../gamma", "gamma corp", "1gamma", ""])
def test_the_client_name_is_a_folder_safe_slug(client: str) -> None:
    with pytest.raises(ValidationError):
        _doc(client=client)


def test_a_discovery_is_frozen_and_rejects_unknown_fields() -> None:
    doc = _doc()
    with pytest.raises(ValidationError):
        doc.sponsor = "someone else"
    with pytest.raises(ValidationError):
        DiscoveryDoc.model_validate({**VALID, "approved": True})
