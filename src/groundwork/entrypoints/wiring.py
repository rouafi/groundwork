"""Composition root: turn a client pack's config into adapters.

The only place that knows which adapter class backs which config name.
Adding a CRM is one entry in `CRM_ADAPTERS` plus the adapter itself.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from groundwork.adapters.crm.fixture import FixtureCrm
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.pack import PackConfig
from groundwork.core.ports.crm import CrmPort
from groundwork.core.services.packs import CONFIG_FILE

FIXTURES_SUBDIR = Path("fixtures") / "hubspot"

CRM_ADAPTERS: Mapping[str, Callable[[Path], CrmPort]] = MappingProxyType(
    {"fixture": lambda pack_dir: FixtureCrm(pack_dir / FIXTURES_SUBDIR)}
)


def build_crm(pack_dir: Path, config: PackConfig) -> CrmPort:
    """Build the CRM adapter the pack selects with `crm:` in its config."""
    factory = CRM_ADAPTERS.get(config.crm)
    if factory is None:
        valid = ", ".join(sorted(CRM_ADAPTERS))
        raise PackError(
            f"{pack_dir / CONFIG_FILE}: unknown crm adapter {config.crm!r} (valid: {valid})"
        )
    return factory(pack_dir)
