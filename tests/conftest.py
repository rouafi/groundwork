"""Mark tests by folder: tests/unit -> unit, tests/contracts -> contract, ...

Live tests call real paid APIs: they are skipped unless selected explicitly with `-m live`.
"""

import pytest

_MARKERS = {"unit": "unit", "contracts": "contract", "integration": "integration", "live": "live"}
_SKIP_LIVE = pytest.mark.skip(reason="live test: run explicitly with `pytest -m live`")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_live = "live" in (config.option.markexpr or "")
    for item in items:
        for folder, marker in _MARKERS.items():
            if f"/tests/{folder}/" in str(item.path):
                item.add_marker(getattr(pytest.mark, marker))
        if not run_live and item.get_closest_marker("live"):
            item.add_marker(_SKIP_LIVE)
