"""The shipped client packs: data only, consistent, inside their domain vocabulary."""

from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import load_domain_pack, load_pack_config

REPO = Path(__file__).resolve().parents[2]
PACKS = sorted(p for p in (REPO / "client_packs").iterdir() if p.is_dir())
DATA_SUFFIXES = {".json", ".yaml", ".yml", ".md"}


def test_client_packs_contain_only_data() -> None:
    files = [p for p in (REPO / "client_packs").rglob("*") if p.is_file()]
    offenders = [str(p.relative_to(REPO)) for p in files if p.suffix not in DATA_SUFFIXES]
    assert offenders == [], f"client packs are data only (JSON, YAML, Markdown): {offenders}"


def test_acme_and_beta_are_shipped() -> None:
    assert {"acme", "beta"} <= {p.name for p in PACKS}


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_pack_facts_are_consistent(pack: Path) -> None:
    config = load_pack_config(pack)
    domain = load_domain_pack(REPO / "domains", config.domain)
    crm = FixtureCrm(pack / "fixtures" / "hubspot")
    assert check_integrity(crm, domain) == ()
