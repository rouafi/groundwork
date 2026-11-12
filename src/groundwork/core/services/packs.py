"""Load client and domain packs from disk into validated domain types."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.golden import ExtractionGolden
from groundwork.core.domain.knowhow import Interview
from groundwork.core.domain.pack import PackConfig

DOMAIN_FILE = "domain.yaml"
CONFIG_FILE = "config.yaml"
PROMPTS_DIR = "prompts"
INTERVIEWS_DIR = "interviews"
EXTRACTION_GOLDEN_FILE = Path("evals") / "extraction_golden.yaml"
FRONT_MATTER = "---\n"


def load_pack_config(pack_dir: Path) -> PackConfig:
    """Read and validate `<pack_dir>/config.yaml`."""
    return _load_yaml_model(pack_dir / CONFIG_FILE, PackConfig)


def load_interviews(pack_dir: Path) -> tuple[Interview, ...]:
    """Read `<pack_dir>/interviews/*.md`: YAML front matter (`id`, `role`), then the transcript.

    The id must equal the file name, so a rule's provenance always names a file.
    A pack without an interviews folder has no interviews.
    """
    folder = pack_dir / INTERVIEWS_DIR
    if not folder.is_dir():
        return ()
    return tuple(_load_interview(path) for path in sorted(folder.glob("*.md")))


def load_extraction_golden(pack_dir: Path) -> ExtractionGolden | None:
    """Read `<pack_dir>/evals/extraction_golden.yaml`, or None when the pack has none."""
    path = pack_dir / EXTRACTION_GOLDEN_FILE
    return _load_yaml_model(path, ExtractionGolden) if path.is_file() else None


def _load_interview(path: Path) -> Interview:
    raw = path.read_text(encoding="utf-8")
    head, sep, text = raw.removeprefix(FRONT_MATTER).partition(f"\n{FRONT_MATTER}")
    if not raw.startswith(FRONT_MATTER) or not sep:
        raise PackError(f"{path}: missing YAML front matter (--- id, role ---)")
    try:
        meta = yaml.safe_load(head) or {}
        if not isinstance(meta, dict):
            raise PackError(f"{path}: front matter must be a mapping (id, role)")
        interview = Interview.model_validate({**meta, "text": text})
    except yaml.YAMLError as exc:
        raise PackError(f"{path}: invalid front matter ({exc})") from exc
    except ValidationError as exc:
        raise PackError(f"{path}: {_summarize(exc)}") from exc
    if interview.id != path.stem:
        raise PackError(f"{path}: id {interview.id!r} does not match the file name")
    return interview


def load_domain_pack(domains_dir: Path, name: str) -> DomainPack:
    """Read and validate `<domains_dir>/<name>/domain.yaml`."""
    domain_dir = domains_dir / name
    if not domain_dir.is_dir():
        raise PackError(f"domain {name!r} not found: {domain_dir} does not exist")
    return _load_yaml_model(domain_dir / DOMAIN_FILE, DomainPack)


def load_prompt(domains_dir: Path, domain: str, name: str) -> str:
    """Read `<domains_dir>/<domain>/prompts/<name>.md`."""
    path = domains_dir / domain / PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PackError(f"{path}: prompt not found")
    return path.read_text(encoding="utf-8")


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
