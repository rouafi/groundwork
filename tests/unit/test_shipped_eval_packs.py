"""The golden sets, rubrics, thresholds and calibration shipped with the demo packs."""

from pathlib import Path

import pytest

from groundwork.core.services.packs import (
    load_calibration,
    load_golden,
    load_rubric,
    load_thresholds,
)

PACKS = Path(__file__).resolve().parents[2] / "client_packs"


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_a_shipped_pack_has_a_full_golden_set(pack: str) -> None:
    cases = load_golden(PACKS / pack)
    assert len(cases) == 20
    adversarial = [c for c in cases if "adversarial" in c.tags]
    assert len(adversarial) == 6
    assert sum("injection" in c.tags for c in adversarial) == 2
    assert len({c.id for c in cases}) == 20


@pytest.mark.parametrize("pack", ["acme", "beta"])
def test_a_shipped_pack_has_a_rubric_thresholds_and_calibration(pack: str) -> None:
    assert load_rubric(PACKS / pack)
    assert load_thresholds(PACKS / pack) is not None
    calibration = load_calibration(PACKS / pack)
    assert len(calibration) == 5
    assert len({c.human_tone for c in calibration}) >= 3  # labels span the scale
