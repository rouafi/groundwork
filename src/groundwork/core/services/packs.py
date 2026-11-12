"""Load client and domain packs from disk into validated domain types."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, RootModel, ValidationError

from groundwork.core.domain.domain_pack import DomainPack
from groundwork.core.domain.errors import PackError
from groundwork.core.domain.evals import GoldenCase, Thresholds
from groundwork.core.domain.golden import ExtractionGolden
from groundwork.core.domain.harmonize import DemoCase
from groundwork.core.domain.knowhow import Interview, Rule
from groundwork.core.domain.pack import PackConfig
from groundwork.core.domain.policy import Policies, PolicyOverrides
from groundwork.core.domain.search import Chunk, RetrievalQuestion

DOMAIN_FILE = "domain.yaml"
CONFIG_FILE = "config.yaml"
PROMPTS_DIR = "prompts"
INTERVIEWS_DIR = "interviews"
EXTRACTION_GOLDEN_FILE = Path("evals") / "extraction_golden.yaml"
RULES_FILE = "rules.yaml"
POLICIES_FILE = "policies.yaml"
DEMO_FILE = "demo_cases.json"
GOLDEN_FILE = "golden.jsonl"
THRESHOLDS_FILE = "thresholds.yaml"
RUBRIC_FILE = "rubric.md"
CHUNKS_FILE = Path("index") / "chunks.jsonl"
RETRIEVAL_FILE = "retrieval.jsonl"
FRONT_MATTER = "---\n"


class _Rules(RootModel[tuple[Rule, ...]]):
    """Schema of `rules.yaml`: a list of rules."""


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


def load_rules(pack_dir: Path) -> tuple[Rule, ...]:
    """Read `<pack_dir>/rules.yaml`, a list of rules. A pack without it has no rules yet."""
    path = pack_dir / RULES_FILE
    if not path.is_file():
        return ()
    return _load_yaml_model(path, _Rules).root


def load_chunks(pack_dir: Path) -> tuple[Chunk, ...]:
    """Read `<pack_dir>/index/chunks.jsonl`. A pack that was never indexed has no chunks."""
    return _load_jsonl(pack_dir / CHUNKS_FILE, Chunk)


def load_retrieval_questions(pack_dir: Path) -> tuple[RetrievalQuestion, ...]:
    """Read `<pack_dir>/retrieval.jsonl`. A pack without questions has none."""
    return _load_jsonl(pack_dir / RETRIEVAL_FILE, RetrievalQuestion)


def _load_jsonl[M: BaseModel](path: Path, model: type[M]) -> tuple[M, ...]:
    if not path.is_file():
        return ()
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            items.append(model.model_validate_json(line))
        except ValidationError as exc:
            raise PackError(f"{path}:{number}: {_summarize(exc)}") from exc
    return tuple(items)


def load_golden(pack_dir: Path) -> tuple[GoldenCase, ...]:
    """Read `<pack_dir>/golden.jsonl`, one case per line. A pack without it has none."""
    cases = _load_jsonl(pack_dir / GOLDEN_FILE, GoldenCase)
    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        raise PackError(f"{pack_dir / GOLDEN_FILE}: duplicate case ids {duplicates}")
    return cases


def load_thresholds(pack_dir: Path) -> Thresholds | None:
    """Read `<pack_dir>/thresholds.yaml`, or None when the pack states none."""
    path = pack_dir / THRESHOLDS_FILE
    return _load_yaml_model(path, Thresholds) if path.is_file() else None


def load_rubric(pack_dir: Path) -> str | None:
    """Read `<pack_dir>/rubric.md`, the tone rubric of the judge, or None."""
    path = pack_dir / RUBRIC_FILE
    return path.read_text(encoding="utf-8") if path.is_file() else None


def load_demo_cases(pack_dir: Path) -> tuple[DemoCase, ...]:
    """Read `<pack_dir>/demo_cases.json`, a list of cases. A pack without it has none."""
    path = pack_dir / DEMO_FILE
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise PackError(f"{path}: not a JSON list of demo cases")
        cases = tuple(DemoCase.model_validate(item) for item in raw)
    except json.JSONDecodeError as exc:
        raise PackError(f"{path}: not a JSON list of demo cases ({exc})") from exc
    except ValidationError as exc:
        raise PackError(f"{path}: {_summarize(exc)}") from exc
    ids = [c.case_id for c in cases]
    if len(set(ids)) != len(ids):
        raise PackError(f"{path}: case ids must be unique")
    return cases


def load_domain_policies(domains_dir: Path, domain: str) -> Policies:
    """Read `<domains_dir>/<domain>/policies.yaml`, the domain defaults. Missing means core only."""
    path = domains_dir / domain / POLICIES_FILE
    return _load_yaml_model(path, Policies) if path.is_file() else Policies()


def load_pack_policies(pack_dir: Path) -> PolicyOverrides | None:
    """Read `<pack_dir>/policies.yaml`, the client's additions, or None when it has none."""
    path = pack_dir / POLICIES_FILE
    return _load_yaml_model(path, PolicyOverrides) if path.is_file() else None


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
