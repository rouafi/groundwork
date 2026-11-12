"""Pure functions from HubSpot CRM v3 objects to domain types.

Shared by `FixtureCrm` now and by a real `HubSpotCrm` later, so only the
transport changes. Input shape: `{"id": "...", "properties": {...}}`, every
property value a string, as HubSpot returns them.

Documented simplifications (PRD-001):
- contact to company: the property `associatedcompanyid`;
- deal to contact: the first entry of `associations.contacts.results`
  (HubSpot's shape when a deal is read with `associations=contacts`);
- deal products: the property `product_ids`, `;`-separated;
- custom properties: `segment`, `persona`, `currency`, `allowed_claims`
  (`;`-separated) and `notes`.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from groundwork.core.domain.facts import Company, Contact, Deal, Product

LIST_SEPARATOR = ";"


class MappingError(ValueError):
    """A raw HubSpot object cannot become a domain type."""

    def __init__(self, kind: str, id: str, detail: str) -> None:
        self.kind = kind
        self.id = id
        super().__init__(f"{kind} {id}: {detail}")


def to_company(raw: object) -> Company:
    obj_id, props, _ = _unwrap(raw, "company")
    fields = {
        "id": obj_id,
        "name": props.get("name"),
        "segment": props.get("segment"),
        "country": props.get("country"),
    }
    return _build(Company, "company", obj_id, fields)


def to_contact(raw: object) -> Contact:
    obj_id, props, _ = _unwrap(raw, "contact")
    fields = {
        "id": obj_id,
        "first_name": props.get("firstname"),
        "last_name": props.get("lastname"),
        "email": props.get("email"),
        "company_id": props.get("associatedcompanyid"),
        "persona": props.get("persona"),
        "notes": props.get("notes") or "",
    }
    return _build(Contact, "contact", obj_id, fields)


def to_product(raw: object) -> Product:
    obj_id, props, _ = _unwrap(raw, "product")
    fields = {
        "id": obj_id,
        "name": props.get("name"),
        "description": props.get("description") or "",
        "price": props.get("price"),
        "currency": props.get("currency"),
        "allowed_claims": _split(props.get("allowed_claims"), "product", obj_id),
    }
    return _build(Product, "product", obj_id, fields)


def to_deal(raw: object) -> Deal:
    obj_id, props, obj = _unwrap(raw, "deal")
    fields = {
        "id": obj_id,
        "contact_id": _primary_contact(obj, obj_id),
        "name": props.get("dealname"),
        "stage": props.get("dealstage"),
        "amount": props.get("amount"),
        "product_ids": _split(props.get("product_ids"), "deal", obj_id),
    }
    return _build(Deal, "deal", obj_id, fields)


def _unwrap(raw: object, kind: str) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    """Return the id, the properties and the whole object, or raise on a malformed object."""
    if not isinstance(raw, Mapping):
        raise MappingError(kind, "?", "expected an object with 'id' and 'properties'")
    obj_id = raw.get("id")
    if not isinstance(obj_id, str) or not obj_id:
        raise MappingError(kind, "?", "missing or empty 'id'")
    props = raw.get("properties")
    if not isinstance(props, Mapping):
        raise MappingError(kind, obj_id, "missing 'properties' object")
    return obj_id, props, raw


def _primary_contact(raw: Mapping[str, Any], deal_id: str) -> str:
    try:
        contact_id = raw["associations"]["contacts"]["results"][0]["id"]
    except (KeyError, IndexError, TypeError):
        raise MappingError(
            "deal", deal_id, "no contact in 'associations.contacts.results'"
        ) from None
    if not isinstance(contact_id, str):
        raise MappingError("deal", deal_id, "contact association id must be a string")
    return contact_id


def _split(value: object, kind: str, obj_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, str):
        raise MappingError(kind, obj_id, f"expected a {LIST_SEPARATOR!r}-separated string")
    return tuple(part.strip() for part in value.split(LIST_SEPARATOR) if part.strip())


def _build[M: BaseModel](model: type[M], kind: str, obj_id: str, fields: dict[str, Any]) -> M:
    try:
        return model.model_validate(fields)
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise MappingError(kind, obj_id, detail) from exc
