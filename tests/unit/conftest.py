from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.harmonize import ContextPack
from groundwork.core.services.context import contact_context
from groundwork.core.services.context_pack import build_context_pack
from groundwork.core.services.packs import load_rules

ACME = Path(__file__).resolve().parents[2] / "client_packs" / "acme"


@pytest.fixture(scope="session")
def pack() -> ContextPack:
    """The context pack of an acme contact for an external email."""
    context = contact_context(FixtureCrm(ACME / "fixtures" / "hubspot"), "acme-c-1")
    return build_context_pack(context, load_rules(ACME), (), "external")
