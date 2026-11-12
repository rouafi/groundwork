from pathlib import Path

import pytest

from groundwork.core.domain.errors import PackError
from groundwork.core.domain.policy import (
    CORE_MAX_STEPS,
    CORE_TIMEOUT_S,
    ForbiddenPatterns,
    LimitOverrides,
    Policies,
    PolicyOverrides,
)
from groundwork.core.services.packs import load_domain_policies, load_pack_policies
from groundwork.core.services.policy import merge_policies

DOMAINS = Path(__file__).resolve().parents[2] / "domains"

DOMAIN = Policies(
    forbidden_patterns=ForbiddenPatterns(internal=("a",), external=("x", "y")),
    limits={"max_steps": 6, "max_tokens": 40000, "timeout_s": 30},  # type: ignore[arg-type]
)


def test_without_overrides_the_domain_defaults_apply() -> None:
    assert merge_policies(DOMAIN, None) == DOMAIN


def test_patterns_accumulate_domain_first_without_duplicates() -> None:
    client = PolicyOverrides(
        forbidden_patterns=ForbiddenPatterns(external=("y", "z"), internal=("b",))
    )
    merged = merge_policies(DOMAIN, client)
    assert merged.forbidden_patterns.external == ("x", "y", "z")
    assert merged.forbidden_patterns.internal == ("a", "b")


def test_a_client_can_lower_limits_and_never_raise_them() -> None:
    lowered = merge_policies(
        DOMAIN, PolicyOverrides(limits=LimitOverrides(max_steps=3, timeout_s=10))
    )
    assert (lowered.limits.max_steps, lowered.limits.timeout_s, lowered.limits.max_tokens) == (
        3,
        10,
        40000,
    )
    raised = merge_policies(
        DOMAIN, PolicyOverrides(limits=LimitOverrides(max_steps=8, timeout_s=60))
    )
    assert (raised.limits.max_steps, raised.limits.timeout_s) == (6, 30)


def test_a_client_can_turn_internal_auto_send_off_but_not_back_on() -> None:
    assert (
        merge_policies(DOMAIN, PolicyOverrides(auto_send_internal=False)).auto_send_internal
        is False
    )
    assert merge_policies(DOMAIN, PolicyOverrides()).auto_send_internal is True
    off = DOMAIN.model_copy(update={"auto_send_internal": False})
    assert merge_policies(off, PolicyOverrides(auto_send_internal=True)).auto_send_internal is False


def test_the_comms_domain_defaults_load_and_block_a_percentage_discount() -> None:
    defaults = load_domain_policies(DOMAINS, "comms")
    assert defaults.forbidden_patterns.external
    assert defaults.limits.max_steps == CORE_MAX_STEPS
    assert defaults.auto_send_internal is True


def test_a_domain_without_policies_gets_the_core_defaults(tmp_path: Path) -> None:
    assert load_domain_policies(tmp_path, "none") == Policies()


def _pack(tmp_path: Path, text: str) -> Path:
    pack = tmp_path / "acme"
    pack.mkdir()
    (pack / "policies.yaml").write_text(text, encoding="utf-8")
    return pack


def test_a_pack_without_policies_has_none(tmp_path: Path) -> None:
    assert load_pack_policies(tmp_path) is None


def test_a_valid_pack_policies_file_loads(tmp_path: Path) -> None:
    pack = _pack(
        tmp_path, "forbidden_patterns:\n  external: ['(?i)guarantee']\nlimits:\n  max_steps: 4\n"
    )
    policies = load_pack_policies(pack)
    assert policies is not None
    assert policies.forbidden_patterns.external == ("(?i)guarantee",)
    assert policies.limits.max_steps == 4


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("auto_send_external: true\n", "auto_send_external"),
        ("external_requires_approval: false\n", "external_requires_approval"),
        ("allow_false_claims: true\n", "allow_false_claims"),
        ("forbidden_patterns:\n  any: ['x']\n", "any"),
        (f"limits:\n  max_steps: {CORE_MAX_STEPS + 1}\n", "max_steps"),
        (f"limits:\n  timeout_s: {CORE_TIMEOUT_S + 1}\n", "timeout_s"),
        ("limits:\n  max_steps: 0\n", "max_steps"),
        ("forbidden_patterns:\n  external: ['(unclosed']\n", "invalid regular expression"),
    ],
)
def test_a_policies_file_cannot_weaken_an_invariant_and_the_error_names_the_file(
    tmp_path: Path, text: str, needle: str
) -> None:
    pack = _pack(tmp_path, text)
    with pytest.raises(PackError) as error:
        load_pack_policies(pack)
    assert needle in str(error.value)
    assert "policies.yaml" in str(error.value)
