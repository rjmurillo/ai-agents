"""Classifier tests for cells derived from recorded files (issue #5423).

The negative controls: a capture from another runtime version never verifies,
a capture with no event never verifies, and bounds that do not meet never
produce a limit.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.eval._harness_capability_test_support import (
    MATRIX,
    capability,
    context_reset,
    offline,
    rollout,
)
from tests.eval._rollout_test_support import ROLLOUTS

Status = capability.CapabilityStatus
Evidence = capability.EvidenceKind


def _record(harness: str, version: str) -> capability.HarnessCapabilityRecord:
    base = next(r for r in capability.load_matrix(MATRIX) if r.harness == harness)
    return replace(base, version=version, version_evidence=Evidence.BACKEND)


def _ceiling(lower: int = 6, upper: int = 6, version: str = "0.154.0") -> rollout.SpawnCeiling:
    return rollout.SpawnCeiling(
        cli_version=version, lower_bound=lower, upper_bound=upper, refusals=3
    )


def _observation(harness: str, version: str, **counts: int) -> context_reset.ResetObservation:
    fields = {"compactions": 0, "failed_compactions": 0, "truncations": 0, **counts}
    return context_reset.ResetObservation(harness, version, **fields)


# --- Version token -------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "token"),
    [
        ("codex-cli 0.156.0", "0.156.0"),
        ("GitHub Copilot CLI 1.0.89-1.", "1.0.89-1"),
        ("0.154.0", "0.154.0"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_version_token_takes_the_last_word_without_the_period(line: str, token: str) -> None:
    assert offline.version_token(line) == token


# --- Spawn ceiling -------------------------------------------------------------


def test_no_ceiling_is_unverified_with_no_evidence() -> None:
    cell = offline.classify_spawn_ceiling(None, _record("codex", "codex-cli 0.154.0"))

    assert (cell.status, cell.evidence) == (Status.UNVERIFIED, Evidence.NONE)


def test_an_exact_ceiling_at_the_pinned_version_verifies() -> None:
    record = _record("codex", "codex-cli 0.154.0")

    cell = offline.classify_spawn_ceiling(_ceiling(), record)

    assert (cell.status, cell.evidence, cell.value) == (Status.VERIFIED, Evidence.BACKEND, 6)
    capability.validate_record(
        replace(record, capabilities={**record.capabilities, "concurrency_limit": cell})
    )


def test_an_exact_ceiling_from_another_version_never_verifies() -> None:
    cell = offline.classify_spawn_ceiling(_ceiling(), _record("codex", "codex-cli 0.156.0"))

    assert cell.status is Status.UNVERIFIED
    assert cell.value is None
    assert "0.154.0" in cell.detail
    assert "0.156.0" in cell.detail


def test_bounds_that_do_not_meet_never_verify_even_at_the_pinned_version() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(lower=3, upper=6), _record("codex", "codex-cli 0.154.0")
    )

    assert cell.status is Status.UNVERIFIED
    assert cell.value is None
    assert "between 3 and 6" in cell.detail


def test_a_record_with_no_version_never_matches_a_ceiling() -> None:
    cell = offline.classify_spawn_ceiling(_ceiling(), _record("codex", ""))

    assert cell.status is Status.UNVERIFIED


# --- Context reset -------------------------------------------------------------


def test_no_events_is_unverified_with_no_evidence() -> None:
    cell = offline.classify_context_reset(
        _observation("codex", "0.154.0"), _record("codex", "codex-cli 0.154.0")
    )

    assert (cell.status, cell.evidence) == (Status.UNVERIFIED, Evidence.NONE)


def test_events_at_the_pinned_version_verify() -> None:
    record = _record("copilot", "GitHub Copilot CLI 1.0.79-9.")

    cell = offline.classify_context_reset(
        _observation("copilot", "1.0.79-9", compactions=1), record
    )

    assert (cell.status, cell.evidence) == (Status.VERIFIED, Evidence.BACKEND)
    capability.validate_record(
        replace(record, capabilities={**record.capabilities, "context_reset_observability": cell})
    )


def test_a_truncation_alone_is_observable_context_loss() -> None:
    cell = offline.classify_context_reset(
        _observation("copilot", "1.0.79-9", truncations=1),
        _record("copilot", "GitHub Copilot CLI 1.0.79-9"),
    )

    assert cell.status is Status.VERIFIED


def test_events_from_another_version_never_verify() -> None:
    cell = offline.classify_context_reset(
        _observation("copilot", "1.0.79-9", compactions=1),
        _record("copilot", "GitHub Copilot CLI 1.0.89-1."),
    )

    assert cell.status is Status.UNVERIFIED
    assert "1.0.79-9" in cell.detail
    assert "1.0.89-1" in cell.detail


def test_an_observation_for_the_other_harness_is_a_caller_error() -> None:
    with pytest.raises(ValueError, match="observation is for codex, record is copilot"):
        offline.classify_context_reset(
            _observation("codex", "0.154.0", compactions=1),
            _record("copilot", "GitHub Copilot CLI 1.0.89-1."),
        )


def test_recorded_codex_rollout_at_a_matching_pin_verifies() -> None:
    observed = context_reset.observe_codex_rollout(
        rollout.load_rollout(ROLLOUTS / "compaction.rollout.jsonl")
    )

    cell = offline.classify_context_reset(observed, _record("codex", "codex-cli 0.154.0"))

    assert cell.status is Status.VERIFIED
