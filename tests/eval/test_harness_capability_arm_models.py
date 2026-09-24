"""Arm `required_models` coverage (issue #5423 scope addition).

`derive_arm_eligibility` used to reach `ELIGIBLE_MATCHED` for any two
harnesses whose required capabilities were all `VERIFIED`, even when neither
harness ever ran the arm's actual model family: the checked-in matrix's
Copilot record has no Sol/Luna/Terra model at all (BYOK Anthropic routes to
Claude only), so an arm comparing Codex against Copilot could read as
matched on capability status alone while comparing two entirely different
model families. `Arm.required_models` and the model-family gate in
`derive_arm_eligibility` close that gap; these tests are split out of
`test_harness_capability.py`, which is already at the file-size ceiling.
"""

from __future__ import annotations

from dataclasses import replace

from tests.eval._harness_capability_test_support import MATRIX, capability

ArmEligibility = capability.ArmEligibility
Capability = capability.Capability
CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
HarnessCapabilityRecord = capability.HarnessCapabilityRecord


def _verified_cap(value: int | None = None, detail: str = "") -> Capability:
    return Capability(
        status=CapabilityStatus.VERIFIED,
        evidence=EvidenceKind.BACKEND,
        detail=detail,
        value=value,
    )


def _record(harness: str, supported_models: tuple[str, ...]) -> HarnessCapabilityRecord:
    caps: dict[str, Capability] = {}
    for key in capability.CAPABILITY_KEYS:
        if key == "concurrency_limit":
            caps[key] = _verified_cap(value=3)
        elif key == "sol_ultra":
            caps[key] = _verified_cap(detail="exact Sol Ultra control observed")
        else:
            caps[key] = _verified_cap()
    return HarnessCapabilityRecord(
        harness=harness,
        version=f"{harness} 1.0.0",
        version_evidence=EvidenceKind.BACKEND,
        supported_models=supported_models,
        supported_efforts=("high",),
        capabilities=caps,
        tool_sandbox_constraints="",
        telemetry_fields=("tokens",),
        failure_retry_behavior="retry once",
        probe_command="probe",
        date="2026-09-24",
    )


def _arm(arm_id: str) -> capability.Arm:
    return next(arm for arm in capability.ARMS if arm.arm_id == arm_id)


# --- Positive: both harnesses cover the arm's model family --------------------


def test_arm_a_matches_when_both_harnesses_cover_the_sol_family() -> None:
    codex = _record("codex", ("gpt-5.6-sol", "gpt-6-luna"))
    copilot = _record("copilot", ("gpt-5.6-sol",))
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.ELIGIBLE_MATCHED
    )


def test_arm_b_matches_when_both_harnesses_cover_sol_and_an_any_of_worker() -> None:
    # B's second group is any-of (luna, terra): each harness satisfies it
    # independently, so codex covering luna and copilot covering terra both
    # count, the same way one harness offering only luna still counts.
    codex = _record("codex", ("gpt-5.6-sol", "gpt-6-luna"))
    copilot = _record("copilot", ("gpt-5.6-sol", "gpt-6-luna"))
    assert (
        capability.derive_arm_eligibility(_arm("B"), codex, copilot)
        is ArmEligibility.ELIGIBLE_MATCHED
    )
    copilot_terra = _record("copilot", ("gpt-5.6-sol", "gpt-5.6-terra"))
    assert (
        capability.derive_arm_eligibility(_arm("B"), codex, copilot_terra)
        is ArmEligibility.ELIGIBLE_MATCHED
    ), "luna and terra are both members of B's any-of worker group"


# --- Negative: a Claude-only harness never satisfies a Sol requirement --------


def test_arm_a_is_unverified_when_the_peer_has_no_sol_model() -> None:
    codex = _record("codex", ("gpt-5.6-sol",))
    copilot = _record("copilot", ("claude-haiku-4-5-20251001", "claude-sonnet-4-6"))
    # Every required capability is VERIFIED on both sides; only the model
    # family is missing. Without the gate this would read ELIGIBLE_MATCHED.
    assert capability.derive_arm_eligibility(_arm("A"), codex, copilot) is ArmEligibility.UNVERIFIED


def test_no_arm_matches_codex_against_the_checked_in_copilot_record() -> None:
    """Every #5422 arm requires a Sol model; the checked-in Copilot record has none."""
    records = {record.harness: record for record in capability.load_matrix(MATRIX)}
    codex = records["codex"]
    copilot = records["copilot"]
    for arm in capability.ARMS:
        assert capability.derive_arm_eligibility(arm, codex, copilot) is not (
            ArmEligibility.ELIGIBLE_MATCHED
        ), f"arm {arm.arm_id} matched codex against a Sol-less copilot record"


# --- Edge: a substring must not satisfy a whole-token family requirement ------


def test_a_model_family_token_must_be_a_whole_path_segment_not_a_substring() -> None:
    # "solar-1".split("-") == {"solar", "1"}; neither equals "sol".
    codex = _record("codex", ("gpt-5.6-sol",))
    copilot = _record("copilot", ("solar-1",))
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot) is ArmEligibility.UNVERIFIED
    ), "solar-1 must not satisfy a sol family requirement by substring aliasing"


def test_required_models_is_checked_after_unsupported_and_before_matched() -> None:
    """Precedence: UNSUPPORTED beats a missing model family, which beats MATCHED."""
    codex = _record("codex", ("gpt-5.6-sol",))
    copilot = _record("copilot", ("claude-haiku-4-5-20251001",))
    unsupported_capabilities = dict(copilot.capabilities)
    unsupported_capabilities["model_override"] = Capability(
        status=CapabilityStatus.UNSUPPORTED, evidence=EvidenceKind.BACKEND
    )
    copilot = replace(copilot, capabilities=unsupported_capabilities)
    # UNSUPPORTED outranks the missing-model-family UNVERIFIED that a Claude-
    # only copilot record would otherwise produce for arm A.
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot) is ArmEligibility.UNSUPPORTED
    )
