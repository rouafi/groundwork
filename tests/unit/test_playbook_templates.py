import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from groundwork.core.domain.discovery import DiscoveryDoc
from groundwork.core.domain.pack import PackConfig

PLAYBOOK = Path(__file__).resolve().parents[2] / "playbook"


def _filled(name: str, client: str = "gamma", domain: str = "comms") -> str:
    text = (PLAYBOOK / name).read_text(encoding="utf-8")
    return text.replace("__CLIENT__", client).replace("__DOMAIN__", domain)


def test_the_discovery_template_fails_validation_and_names_each_unfilled_field() -> None:
    data = yaml.safe_load(_filled("discovery.template.yaml"))
    with pytest.raises(ValidationError) as error:
        DiscoveryDoc.model_validate(data)
    named = {".".join(str(p) for p in e["loc"]) for e in error.value.errors()}
    assert named == {
        "sponsor", "use_case", "users", "channels", "systems", "risks",
        "success_metric.name", "success_metric.baseline", "success_metric.target",
    }  # fmt: skip


def test_the_discovery_template_never_arrives_signed() -> None:
    data = yaml.safe_load(_filled("discovery.template.yaml"))
    assert data["status"] == "draft" and data["signed_off_by"] is None


def test_the_discovery_template_with_every_field_filled_is_a_valid_draft() -> None:
    data = yaml.safe_load(_filled("discovery.template.yaml"))
    data |= {
        "sponsor": "Head of success", "use_case": "Harmonize customer emails.",
        "users": ["account managers"], "channels": ["external"],
        "systems": [{"name": "HubSpot", "role": "contacts"}],
        "success_metric": {"name": "corrections", "baseline": "30%", "target": "10%"},
        "risks": ["a wrong price"],
    }  # fmt: skip
    assert DiscoveryDoc.model_validate(data).status == "draft"


def test_the_config_template_is_a_valid_pack_config_for_the_chosen_client_and_domain() -> None:
    config = PackConfig.model_validate(
        yaml.safe_load(_filled("config.template.yaml", "gamma", "comms"))
    )
    assert config.domain == "comms" and config.internal_recipient == "handoffs@gamma.example"
    assert (config.model, config.embedding) == ("replay", "replay")


@pytest.mark.parametrize("name", ["discovery.template.yaml", "config.template.yaml"])
def test_every_placeholder_of_a_template_is_one_that_new_pack_fills(name: str) -> None:
    left = re.findall(r"__[A-Z]+__", _filled(name))
    assert left == []


def test_the_go_live_checklist_has_only_unticked_boxes() -> None:
    boxes = re.findall(r"^- \[(.)\]", (PLAYBOOK / "go-live-checklist.md").read_text(), flags=re.M)
    assert len(boxes) >= 10
    assert set(boxes) == {" "}


def test_the_interview_script_explains_the_transcript_format_and_the_human_review() -> None:
    script = (PLAYBOOK / "interview-script.md").read_text(encoding="utf-8")
    for needle in ("id:", "role:", "interviews/", "extract-rules", "status: approved"):
        assert needle in script
