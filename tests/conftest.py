"""Mark tests by folder: tests/unit -> unit, tests/contracts -> contract, ..."""

import pytest

_MARKERS = {"unit": "unit", "contracts": "contract", "integration": "integration", "live": "live"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for folder, marker in _MARKERS.items():
            if f"/tests/{folder}/" in str(item.path):
                item.add_marker(getattr(pytest.mark, marker))
