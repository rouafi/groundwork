"""Load client and domain packs from disk into validated domain types."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.pack import PackConfig

DOMAIN_FILE = "domain.yaml"
CONFIG_FILE = "config.yaml"


def load_pack_config(pack_dir: Path) -> PackConfig:
    """Read and validate `<pack_dir>/config.yaml`."""
    return _load_yaml_model(pack_dir / CONFIG_FILE, PackConfig)


def load_domain_pack(domains_dir: Path, name: str) -> DomainPack:
    """Read and validate `<domains_dir>/<name>/domain.yaml`."""
    domain_dir = domains_dir / name
    if not domain_dir.is_dir():
        raise PackError(f"domain {name!r} not found: {domain_dir} does not exist")
    return _load_yaml_model(domain_dir / DOMAIN_FILE, DomainPack)


def _load_yaml_model[M: BaseModel](path: Path, model: type[M]) -> M:
    data = _read_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise PackError(f"{path}: {_summarize(exc)}") from exc


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise PackError(f"{path}: file not found")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"{path}: invalid YAML ({exc})") from exc


def _summarize(exc: ValidationError) -> str:
    """One line per problem, field path first, so the FDE knows what to fix."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}" for err in exc.errors()
    )
