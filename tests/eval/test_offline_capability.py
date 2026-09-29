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
        cli_version=version,
        lower_bound=lower,
        upper_bound=upper,
        refusals=3,
        captured_on="2026-09-10",
    )


def _observation(harness: str, version: str, **counts: int) -> context_reset.ResetObservation:
    fields = {"compactions": 0, "failed_compactions": 0, "truncations": 0, **counts}
    return context_reset.ResetObservation(harness, version, captured_on="2026-08-11", **fields)


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


def test_a_configured_cap_that_was_reached_and_refused_verifies() -> None:
    record = _record("codex", "codex-cli 0.154.0")

    cell = offline.classify_spawn_ceiling(_ceiling(), record, configured_max_threads=6)

    assert (cell.status, cell.evidence, cell.value) == (Status.VERIFIED, Evidence.BACKEND, 6)
    assert cell.date == "2026-09-10"
    cells = {**record.capabilities, "concurrency_limit": cell}
    capability.validate_record(replace(record, capabilities=cells))


def test_an_unknown_session_cap_never_verifies_at_the_pinned_version() -> None:
    cell = offline.classify_spawn_ceiling(_ceiling(), _record("codex", "codex-cli 0.154.0"))

    assert cell.status is Status.UNVERIFIED
    assert cell.value is None
    assert "agents.max_threads is not recorded" in cell.detail


def test_a_peak_below_the_configured_cap_never_verifies() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(lower=3, upper=3), _record("codex", "codex-cli 0.154.0"), configured_max_threads=6
    )

    assert cell.status is Status.UNVERIFIED
    assert "configured agents.max_threads=6" in cell.detail
    assert "3 children ran" in cell.detail


def test_a_peak_above_the_configured_cap_never_verifies() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(lower=8, upper=8), _record("codex", "codex-cli 0.154.0"), configured_max_threads=6
    )

    assert cell.status is Status.UNVERIFIED


def test_the_rollout_upper_bound_never_decides() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(lower=3, upper=6), _record("codex", "codex-cli 0.154.0"), configured_max_threads=3
    )

    assert cell.status is Status.VERIFIED
    assert cell.value == 3


def test_a_configured_ceiling_from_another_version_never_verifies() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(), _record("codex", "codex-cli 0.156.0"), configured_max_threads=6
    )

    assert cell.status is Status.UNVERIFIED
    assert cell.value is None
    assert "0.154.0" in cell.detail
    assert "0.156.0" in cell.detail


def test_a_record_with_no_version_never_matches_a_ceiling() -> None:
    cell = offline.classify_spawn_ceiling(
        _ceiling(), _record("codex", ""), configured_max_threads=6
    )

    assert cell.status is Status.UNVERIFIED


# --- Context reset -------------------------------------------------------------


def test_only_failed_compactions_is_unverified_and_says_so() -> None:
    cell = offline.classify_context_reset(
        _observation("copilot", "1.0.79-9", failed_compactions=2),
        _record("copilot", "GitHub Copilot CLI 1.0.79-9"),
    )

    assert (cell.status, cell.evidence) == (Status.UNVERIFIED, Evidence.NONE)
    assert "2 compaction attempt(s) failed" in cell.detail


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
    assert cell.date == "2026-08-11"
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
