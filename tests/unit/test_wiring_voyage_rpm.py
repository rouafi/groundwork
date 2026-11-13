import pytest

from groundwork.core.domain.errors import PackError
from groundwork.entrypoints.wiring import _voyage_rpm


def test_the_voyage_rate_is_read_from_the_environment() -> None:
    assert _voyage_rpm({}) is None
    assert _voyage_rpm({"VOYAGE_RPM": "3"}) == 3


@pytest.mark.parametrize("value", ["0", "-1", "fast"])
def test_a_bad_voyage_rate_is_refused(value: str) -> None:
    with pytest.raises(PackError, match="VOYAGE_RPM"):
        _voyage_rpm({"VOYAGE_RPM": value})
