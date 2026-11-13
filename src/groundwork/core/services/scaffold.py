"""Create the skeleton of a new client pack from the playbook templates.

The skeleton is data only (CLAUDE.md rule 2): a config, a discovery document, a go-live
checklist and the empty folders the next days fill. It fails validation, with messages that
name what is missing, until a person fills it. It is built in a hidden folder and moved into
place, so a failure never leaves half a pack behind.
"""

import os
import re
import shutil
from pathlib import Path

from groundwork.core.domain.errors import PackError
from groundwork.core.services.packs import load_domain_pack

CLIENT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
TEMPLATES = {
    "config.yaml": "config.template.yaml",
    "discovery.yaml": "discovery.template.yaml",
    "go_live.md": "go-live-checklist.md",
}
EMPTY_DIRS = ("interviews", "fixtures/hubspot")


def scaffold_pack(
    client: str, domain: str, packs_dir: Path, domains_dir: Path, playbook_dir: Path
) -> tuple[Path, ...]:
    """Create `<packs_dir>/<client>/` and return the files and folders it holds.

    Raises `PackError` for a bad name, an unknown domain, a pack that already exists or a
    missing template.
    """
    if not CLIENT_NAME.match(client):
        raise PackError(
            f"invalid client name {client!r}: lowercase letters, digits and dashes, "
            "starting with a letter"
        )
    load_domain_pack(domains_dir, domain)
    target = packs_dir / client
    if target.exists():
        raise PackError(f"{target} already exists: new-pack never overwrites a pack")
    templates = {name: _read(playbook_dir / template) for name, template in TEMPLATES.items()}

    building = packs_dir / f".new-{client}"
    shutil.rmtree(building, ignore_errors=True)
    try:
        building.mkdir(parents=True)
        for name, text in templates.items():
            filled = text.replace("__CLIENT__", client).replace("__DOMAIN__", domain)
            (building / name).write_text(filled, encoding="utf-8")
        for folder in EMPTY_DIRS:
            (building / folder).mkdir(parents=True)
        os.rename(building, target)
    finally:
        shutil.rmtree(building, ignore_errors=True)
    return (*(target / name for name in TEMPLATES), *(target / f for f in EMPTY_DIRS))


def _read(path: Path) -> str:
    if not path.is_file():
        raise PackError(f"playbook template not found: {path}")
    return path.read_text(encoding="utf-8")
