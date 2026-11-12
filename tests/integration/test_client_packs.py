"""The shipped client packs: data only, consistent, inside their domain vocabulary."""

from pathlib import Path

import pytest

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.services.golden_checks import golden_problems
from groundwork.core.services.integrity import check_integrity
from groundwork.core.services.packs import (
    load_domain_pack,
    load_extraction_golden,
    load_interviews,
    load_pack_config,
)

REPO = Path(__file__).resolve().parents[2]
PACKS = sorted(p for p in (REPO / "client_packs").iterdir() if p.is_dir())
DATA_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md"}


def test_client_packs_contain_only_data() -> None:
    files = [p for p in (REPO / "client_packs").rglob("*") if p.is_file()]
    offenders = [str(p.relative_to(REPO)) for p in files if p.suffix not in DATA_SUFFIXES]
    assert offenders == [], (
        f"client packs are data only (JSON, JSON Lines, YAML, Markdown): {offenders}"
    )


def test_acme_and_beta_are_shipped() -> None:
    assert {"acme", "beta"} <= {p.name for p in PACKS}


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_pack_facts_are_consistent(pack: Path) -> None:
    config = load_pack_config(pack)
    domain = load_domain_pack(REPO / "domains", config.domain)
    crm = FixtureCrm(pack / "fixtures" / "hubspot")
    assert check_integrity(crm, domain) == ()


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_interviews_and_extraction_golden_data_agree(pack: Path) -> None:
    interviews = {i.id: i for i in load_interviews(pack)}
    assert len(interviews) == 3
    assert all(300 <= len(i.text.split()) <= 500 for i in interviews.values())
    assert all(i.text.isascii() for i in interviews.values())
    golden = load_extraction_golden(pack)
    assert golden is not None and golden.pack == pack.name
    assert golden_problems(golden, interviews) == []
    expected = [r for gi in golden.interviews for r in gi.expected_rules]
    assert 6 <= len(expected) <= 10
    assert sum(r.kind == "claim" for r in expected) >= 2
    assert sum(r.kind == "tone" for r in expected) >= 2
    assert golden.expected_conflicts and golden.expected_contradictions
    assert any(gi.must_not_extract for gi in golden.interviews)


def test_beta_overrides_the_default_tone_for_mid_market() -> None:
    golden = load_extraction_golden(REPO / "client_packs" / "beta")
    assert golden is not None
    tones = [r for gi in golden.interviews for r in gi.expected_rules if r.kind == "tone"]
    assert any(r.segments == ("mid-market",) and "casual" in r.statement for r in tones)
