"""Facts from the client's systems (CRM), as vendor-neutral domain types.

Facts are the source of truth for names, prices and deal stages. Adapters build
these types from vendor formats; the core never sees vendor JSON.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Id = Annotated[str, Field(min_length=1)]
Money = Annotated[Decimal, Field(ge=0)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class _Fact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Product(_Fact):
    """Something the client sells. `allowed_claims` lists what may be said about it."""

    id: Id
    name: str = Field(min_length=1)
    description: str
    price: Money
    currency: Currency
    allowed_claims: tuple[str, ...]


class Company(_Fact):
    """A customer or prospect organization."""

    id: Id
    name: str = Field(min_length=1)
    segment: str
    country: str


class Contact(_Fact):
    """A person at a company. `notes` is free text from the CRM: untrusted data."""

    id: Id
    first_name: str
    last_name: str
    email: Email
    company_id: Id
    persona: str
    notes: str = ""


class Deal(_Fact):
    """An opportunity with a contact, for one or more products."""

    id: Id
    contact_id: Id
    name: str = Field(min_length=1)
    stage: str
    amount: Money
    product_ids: tuple[Id, ...]


class ContactContext(_Fact):
    """A contact, their company, their deals and the products of those deals."""

    contact: Contact
    company: Company
    deals: tuple[Deal, ...]
    products: tuple[Product, ...]
