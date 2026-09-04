"""Tests for the per-harness capability matrix, issue #5423.

Covers every negative control the issue names, happy-path validation, each
ArmEligibility outcome, schema-version rejection, and malformed-metadata
fail-closed. Assertions target module behavior and the CLI process return
value, not a self-authored fixture, except the one test that pins the honesty
of the checked-in matrix deliverable itself.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import MATRIX, capability, cli

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
ArmEligibility = capability.ArmEligibility
Capability = capability.Capability
HarnessCapabilityRecord = capability.HarnessCapabilityRecord
HarnessCapabilityError = capability.HarnessCapabilityError


def _verified_cap(value: int | None = None, detail: str = "") -> capability.Capability:
    return Capability(
        status=CapabilityStatus.VERIFIED,
        evidence=EvidenceKind.BACKEND,
        detail=detail,
        value=value,
    )


def _record(
    harness: str = "codex",
    *,
    version: str = "codex 1.0.0",
    version_evidence: capability.EvidenceKind = EvidenceKind.BACKEND,
    overrides: dict[str, capability.Capability] | None = None,
) -> capability.HarnessCapabilityRecord:
    caps: dict[str, capability.Capability] = {}
    for key in capability.CAPABILITY_KEYS:
        if key == "concurrency_limit":
            caps[key] = _verified_cap(value=3)
        elif key == "sol_ultra":
            caps[key] = _verified_cap(detail="exact Sol Ultra control observed")
        else:
            caps[key] = _verified_cap()
    if overrides:
        caps.update(overrides)
    return HarnessCapabilityRecord(
        harness=harness,
        version=version,
        version_evidence=version_evidence,
        supported_models=("sol-medium",),
        supported_efforts=("high",),
        capabilities=caps,
        tool_sandbox_constraints="",
        telemetry_fields=("tokens",),
        failure_retry_behavior="retry once",
        probe_command="probe",
        date="2026-08-31",
    )


# --- Happy path ---------------------------------------------------------------


def test_fully_backed_record_validates() -> None:
    capability.validate_record(_record())


def test_load_matrix_reads_checked_in_deliverable() -> None:
    records = capability.load_matrix(MATRIX)
    assert {record.harness for record in records} == {"codex", "copilot"}


def test_checked_in_matrix_claims_nothing_verified() -> None:
    # The deliverable must not ship a VERIFIED claim it did not prove.
    for record in capability.load_matrix(MATRIX):
        assert record.version_evidence is EvidenceKind.NONE
        for cap in record.capabilities.values():
            assert cap.status is CapabilityStatus.UNVERIFIED


# --- Negative control 1: missing runtime identity cannot become VERIFIED ------


def test_no_runtime_version_forbids_verified() -> None:
    record = _record(version="", version_evidence=EvidenceKind.NONE)
    with pytest.raises(HarnessCapabilityError, match="without a backend runtime version"):
        capability.validate_record(record)


# --- Negative control 2: client/schema echo is not backend evidence -----------


def test_verified_requires_backend_evidence() -> None:
    record = _record(
        overrides={
            "model_override": Capability(
                status=CapabilityStatus.VERIFIED,
                evidence=EvidenceKind.CLIENT_ECHO,
            )
        }
    )
    with pytest.raises(HarnessCapabilityError, match="without backend evidence"):
        capability.validate_record(record)


def test_classify_override_rejects_config_echo() -> None:
    status = capability.classify_override(
        "sol-low", "sol-low", EvidenceKind.CONFIG
    )
    assert status is CapabilityStatus.UNVERIFIED


# --- Negative control 3: unsupported effort cannot silently default -----------


def test_effort_that_defaults_to_parent_is_unverified() -> None:
    status = capability.classify_override(
        "high", "medium", EvidenceKind.BACKEND, parent_value="medium"
    )
    assert status is CapabilityStatus.UNVERIFIED


# --- Negative control 5: child model that inherits parent must fail ------------


def test_child_model_silently_inheriting_parent_fails() -> None:
    status = capability.classify_override(
        "luna-high", "sol-medium", EvidenceKind.BACKEND, parent_value="sol-medium"
    )
    assert status is CapabilityStatus.UNVERIFIED


def test_child_model_honored_verifies() -> None:
    status = capability.classify_override(
        "luna-high", "luna-high", EvidenceKind.BACKEND, parent_value="sol-medium"
    )
    assert status is CapabilityStatus.VERIFIED


# --- Negative control 6: reviewer isolation fails on leaked producer context ---


def test_reviewer_isolation_fails_on_leaked_context() -> None:
    status = capability.classify_reviewer_isolation(
        "reviewer sees SECRET_PLAN details", ["SECRET_PLAN"], EvidenceKind.BACKEND
    )
    assert status is CapabilityStatus.UNVERIFIED


def test_reviewer_isolation_verifies_when_clean() -> None:
    status = capability.classify_reviewer_isolation(
        "reviewer sees only the diff", ["SECRET_PLAN"], EvidenceKind.BACKEND
    )
    assert status is CapabilityStatus.VERIFIED


# --- Negative control 4: Sol Ultra alias without evidence -----------------------


def test_sol_ultra_verified_requires_named_control() -> None:
    record = _record(
        overrides={
            "sol_ultra": Capability(
                status=CapabilityStatus.VERIFIED,
                evidence=EvidenceKind.BACKEND,
                detail="",
            )
        }
    )
    with pytest.raises(HarnessCapabilityError, match="sol_ultra is VERIFIED without naming"):
        capability.validate_record(record)


# --- Negative control 7: malformed metadata fails closed ----------------------


def test_unknown_status_string_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["harnesses"][0]["capabilities"]["model_override"]["status"] = "MAYBE"
    doc = tmp_path / "matrix.json"
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HarnessCapabilityError, match="not a valid CapabilityStatus"):
        capability.load_matrix(doc)


def test_capability_value_must_be_integer(tmp_path: Path) -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["harnesses"][0]["capabilities"]["concurrency_limit"]["value"] = "three"
    doc = tmp_path / "matrix.json"
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HarnessCapabilityError, match="value must be an integer"):
        capability.load_matrix(doc)


def test_missing_capability_key_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    del payload["harnesses"][0]["capabilities"]["sol_ultra"]
    doc = tmp_path / "matrix.json"
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HarnessCapabilityError, match="missing keys"):
        capability.load_matrix(doc)


def test_schema_version_mismatch_rejected(tmp_path: Path) -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    doc = tmp_path / "matrix.json"
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HarnessCapabilityError, match="schema_version must be"):
        capability.load_matrix(doc)


def test_concurrency_verified_without_value_rejected() -> None:
    record = _record(
        overrides={
            "concurrency_limit": Capability(
                status=CapabilityStatus.VERIFIED,
                evidence=EvidenceKind.BACKEND,
                value=None,
            )
        }
    )
    with pytest.raises(HarnessCapabilityError, match="concurrency_limit is VERIFIED without"):
        capability.validate_record(record)


# --- Arm eligibility: each of the four outcomes -------------------------------


def _arm(arm_id: str) -> capability.Arm:
    return next(arm for arm in capability.ARMS if arm.arm_id == arm_id)


def test_arm_matched_when_both_verified_and_values_equal() -> None:
    codex = _record("codex")
    copilot = _record("copilot")
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.ELIGIBLE_MATCHED
    )


def test_arm_unmatched_when_concurrency_values_differ() -> None:
    codex = _record("codex")
    copilot = _record(
        "copilot",
        overrides={"concurrency_limit": _verified_cap(value=1)},
    )
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.ELIGIBLE_UNMATCHED
    )


def test_arm_unsupported_when_required_capability_unsupported() -> None:
    codex = _record("codex")
    copilot = _record(
        "copilot",
        overrides={
            "subagent_support": Capability(
                status=CapabilityStatus.UNSUPPORTED, evidence=EvidenceKind.BACKEND
            )
        },
    )
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.UNSUPPORTED
    )


def test_arm_unverified_beats_matched_even_with_same_model_label() -> None:
    # Negative control 8: a matching model label must not infer parity.
    shared = {"supported_models": ("sol-medium",)}
    codex = _record("codex")
    copilot = _record(
        "copilot",
        overrides={
            "subagent_support": Capability(
                status=CapabilityStatus.UNVERIFIED, evidence=EvidenceKind.NONE
            )
        },
    )
    assert codex.supported_models == copilot.supported_models == shared["supported_models"]
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.UNVERIFIED
    )


def test_unsupported_precedence_over_unverified() -> None:
    codex = _record(
        "codex",
        overrides={
            "model_override": Capability(
                status=CapabilityStatus.UNSUPPORTED, evidence=EvidenceKind.BACKEND
            )
        },
    )
    copilot = _record(
        "copilot",
        overrides={
            "effort_override": Capability(
                status=CapabilityStatus.UNVERIFIED, evidence=EvidenceKind.NONE
            )
        },
    )
    assert (
        capability.derive_arm_eligibility(_arm("A"), codex, copilot)
        is ArmEligibility.UNSUPPORTED
    )


# --- build_report -------------------------------------------------------------


def test_build_report_covers_all_six_arms() -> None:
    records = capability.load_matrix(MATRIX)
    report = capability.build_report(records)
    arm_ids = {row["arm"] for row in report["arm_eligibility"]}
    assert arm_ids == {"A", "B", "C", "D", "E", "F"}
    for row in report["arm_eligibility"]:
        assert set(row["eligibility"]) == {"codex", "copilot"}


# --- CLI ----------------------------------------------------------------------


class _FakeRunner:
    """Dispatch a fake CLI response from argv, not from call order."""

    def __init__(self, *, version: str = "copilot 9.9.9", returncode: int = 0) -> None:
        self.version = version
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        args = [str(value) for value in argv]
        self.calls.append(args)
        if "--version" in args:
            return subprocess.CompletedProcess(args, self.returncode, self.version, "")
        raise AssertionError(f"unexpected command: {args}")


def test_cli_dry_run_returns_ok_and_emits_report(capsys) -> None:
    code = cli.main(["--dry-run"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == capability.SCHEMA_VERSION
    assert len(report["arm_eligibility"]) == 6


def test_cli_live_probe_fills_copilot_version(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: "C:/copilot.exe" if name == "copilot" else None
    )
    runner = _FakeRunner()
    code = cli.main(["--output", str(output)], runner=runner)
    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    by_harness = {row["harness"]: row for row in report["harnesses"]}
    assert by_harness["copilot"]["version"] == "copilot 9.9.9"
    assert by_harness["copilot"]["version_evidence"] == "backend"
    # Codex is not probe-capable and stays UNVERIFIED.
    assert by_harness["codex"]["version"] == ""
    assert by_harness["codex"]["version_evidence"] == "none"


def test_cli_probe_failure_leaves_version_unverified(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: "C:/copilot.exe" if name == "copilot" else None
    )
    runner = _FakeRunner(returncode=1)
    code = cli.main(["--output", str(output)], runner=runner)
    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    by_harness = {row["harness"]: row for row in report["harnesses"]}
    assert by_harness["copilot"]["version_evidence"] == "none"


def test_cli_rejects_malformed_matrix(tmp_path: Path) -> None:
    doc = tmp_path / "matrix.json"
    doc.write_text('{"schema_version": 1, "harnesses": []}', encoding="utf-8")
    code = cli.main(["--matrix", str(doc), "--dry-run"])
    assert code == cli.EXIT_CONFIG


def test_cli_rejects_nonpositive_timeout() -> None:
    code = cli.main(["--dry-run", "--timeout", "0"])
    assert code == cli.EXIT_CONFIG


# --- Review-round fixes ---------------------------------------------------------


def test_invalid_utf8_matrix_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "matrix.json"
    doc.write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(HarnessCapabilityError):
        capability.load_matrix(doc)


def test_cli_rejects_invalid_utf8_matrix(tmp_path: Path) -> None:
    doc = tmp_path / "matrix.json"
    doc.write_bytes(b"\xff\xfe not utf-8")
    assert cli.main(["--matrix", str(doc), "--dry-run"]) == cli.EXIT_CONFIG


def test_third_harness_is_not_matched_while_a_peer_is_unmatched() -> None:
    codex = _record("codex")
    copilot = _record(
        "copilot", overrides={"concurrency_limit": _verified_cap(value=5)}
    )
    third = _record("third")
    rows = capability._arm_eligibility_dict([codex, copilot, third])
    arm_a = next(row for row in rows if row["arm"] == "A")
    # "third" matches codex on concurrency and not copilot. Reducing over the
    # first peer alone reported ELIGIBLE_MATCHED and hid the copilot mismatch.
    assert arm_a["eligibility"]["third"] == ArmEligibility.ELIGIBLE_UNMATCHED.value
    assert arm_a["eligibility"]["codex"] == ArmEligibility.ELIGIBLE_UNMATCHED.value
    assert arm_a["eligibility"]["copilot"] == ArmEligibility.ELIGIBLE_UNMATCHED.value


def test_three_agreeing_harnesses_still_match() -> None:
    records = [_record("codex"), _record("copilot"), _record("third")]
    rows = capability._arm_eligibility_dict(records)
    arm_a = next(row for row in rows if row["arm"] == "A")
    assert set(arm_a["eligibility"].values()) == {
        ArmEligibility.ELIGIBLE_MATCHED.value
    }


def test_worst_eligibility_prefers_the_most_restrictive_verdict() -> None:
    assert (
        capability._worst_eligibility(
            [ArmEligibility.ELIGIBLE_MATCHED, ArmEligibility.UNSUPPORTED]
        )
        is ArmEligibility.UNSUPPORTED
    )
    assert (
        capability._worst_eligibility(
            [ArmEligibility.ELIGIBLE_MATCHED, ArmEligibility.ELIGIBLE_UNMATCHED]
        )
        is ArmEligibility.ELIGIBLE_UNMATCHED
    )
    assert capability._worst_eligibility([]) is ArmEligibility.UNVERIFIED
