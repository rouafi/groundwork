"""Test doubles for the ports of the core. Not adapters: they live with the tests."""

import hashlib
import re
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from groundwork.core.domain.errors import NotFoundError
from groundwork.core.domain.facts import Company, Contact, Deal, Product
from groundwork.core.domain.knowhow import Usage
from groundwork.core.ports.model import Answer, CitedStatement, Quote, Tier

CALL_USAGE = Usage(input_tokens=10, output_tokens=5)


def sentences(document: str) -> tuple[CitedStatement, ...]:
    """Default `cite` behaviour: every sentence is a statement quoting itself."""
    return tuple(
        CitedStatement(
            text=m.group(), quotes=(Quote(text=m.group(), start=m.start(), end=m.end()),)
        )
        for m in re.finditer(r"[^.!?\s][^.!?]*[.!?]", document)
    )


class StubModel:
    """Scripted ModelPort. Each behaviour is a function of the call's keyword arguments."""

    def __init__(
        self,
        *,
        structured: Callable[..., Any] | None = None,
        text: Callable[..., str] | None = None,
        cite: Callable[..., tuple[CitedStatement, ...]] | None = None,
    ) -> None:
        self._structured = structured or (lambda **_: {})
        self._text = text or (lambda **_: "")
        self._cite = cite or (lambda **kw: sentences(kw["document"]))
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def complete_structured[S: BaseModel](
        self, *, tier: Tier, system: str, user: str, schema: type[S], document: str | None = None
    ) -> Answer[S]:
        kwargs = {
            "tier": tier,
            "system": system,
            "user": user,
            "schema": schema,
            "document": document,
        }
        self.calls.append(("complete_structured", kwargs))
        return Answer(value=schema.model_validate(self._structured(**kwargs)), usage=CALL_USAGE)

    def complete_text(
        self, *, tier: Tier, system: str, user: str, document: str | None = None
    ) -> Answer[str]:
        kwargs = {"tier": tier, "system": system, "user": user, "document": document}
        self.calls.append(("complete_text", kwargs))
        return Answer(value=self._text(**kwargs), usage=CALL_USAGE)

    def cite(
        self, *, tier: Tier, system: str, instruction: str, document: str
    ) -> Answer[tuple[CitedStatement, ...]]:
        kwargs = {"tier": tier, "system": system, "instruction": instruction, "document": document}
        self.calls.append(("cite", kwargs))
        return Answer(value=self._cite(**kwargs), usage=CALL_USAGE)


class InMemoryCrm:
    def __init__(
        self,
        companies: Iterable[Company] = (),
        contacts: Iterable[Contact] = (),
        deals: Iterable[Deal] = (),
        products: Iterable[Product] = (),
    ) -> None:
        self._companies = {c.id: c for c in companies}
        self._contacts = {c.id: c for c in contacts}
        self._deals = {d.id: d for d in deals}
        self._products = {p.id: p for p in products}

    def get_contact(self, contact_id: str) -> Contact:
        return _get(self._contacts, "contact", contact_id)

    def get_company(self, company_id: str) -> Company:
        return _get(self._companies, "company", company_id)

    def get_deal(self, deal_id: str) -> Deal:
        return _get(self._deals, "deal", deal_id)

    def get_deals(self, contact_id: str) -> tuple[Deal, ...]:
        self.get_contact(contact_id)
        return tuple(d for d in self._deals.values() if d.contact_id == contact_id)

    def get_products(self, product_ids: Sequence[str]) -> tuple[Product, ...]:
        return tuple(_get(self._products, "product", pid) for pid in product_ids)

    def list_contact_ids(self) -> tuple[str, ...]:
        return tuple(self._contacts)

    def list_company_ids(self) -> tuple[str, ...]:
        return tuple(self._companies)

    def list_deal_ids(self) -> tuple[str, ...]:
        return tuple(self._deals)

    def list_product_ids(self) -> tuple[str, ...]:
        return tuple(self._products)


def _get[T](items: dict[str, T], kind: str, id: str) -> T:
    try:
        return items[id]
    except KeyError:
        raise NotFoundError(kind, id) from None


class HashEmbedding:
    """Deterministic EmbeddingPort: eight values derived from a hash of the text and type."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [_hash_vector(t, input_type) for t in texts]


def _hash_vector(text: str, input_type: str) -> list[float]:
    digest = hashlib.sha256(f"{input_type}:{text}".encode()).digest()
    return [(b - 127.5) / 127.5 for b in digest[:8]]
