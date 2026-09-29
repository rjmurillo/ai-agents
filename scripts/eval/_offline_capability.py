"""Capability cells derived from recorded runtime files, no live call.

Two #5423 cells were `UNVERIFIED` with the reason "not triggered": the
concurrency limit and context reset observability. Both CLIs record enough on
disk to answer them for the version that wrote the file. This module turns a
recorded observation into a `Capability`, holding the line the rest of the
matrix holds: `VERIFIED` needs backend evidence at the record's own pinned
runtime version. A capture from another version is a fact about that version
and stays `UNVERIFIED` with the versions named, because "a contract without a
version is not a contract" (`.claude/skills/ai-agents-empirical-probe-toolkit/SKILL.md`).

Evidence kind: both inputs are the runtime's own persisted event stream, the
`BACKEND` class `EvidenceKind` names ("runtime event stream"). No config value
is read, so nothing here can promote a label to a measurement.

Stricter/looser/different than canonical: `apply_behavioral_probe` in
`_harness_capability.py` upgrades a cell from a live probe result. These
classifiers upgrade from a file a past run left behind, so the capture date is
the file's, not today's, and `probe_command` names how to regenerate it.
"""

from __future__ import annotations

import re

from _codex_rollout import SpawnCeiling
from _context_reset import ResetObservation
from _harness_capability import (
    Capability,
    CapabilityStatus,
    EvidenceKind,
    HarnessCapabilityRecord,
)

_TRAILING_PERIOD = re.compile(r"\.+$")


def version_token(version: str) -> str:
    """Return the bare version from a `--version` line, or `""`.

    `codex-cli 0.156.0` gives `0.156.0`. `GitHub Copilot CLI 1.0.89-1.` gives
    `1.0.89-1` (the CLI prints a trailing period).
    """
    parts = version.split()
    return _TRAILING_PERIOD.sub("", parts[-1]) if parts else ""


def _pinned(record: HarnessCapabilityRecord, observed: str) -> bool:
    token = version_token(record.version)
    return bool(token) and token == observed


def _mismatch(record: HarnessCapabilityRecord, observed: str) -> str:
    pinned = version_token(record.version) or "no runtime version"
    return (
        f"Capture is from {observed}; the matrix pins {pinned}, "
        "so it is not evidence for that version."
    )


def classify_spawn_ceiling(
    ceiling: SpawnCeiling | None, record: HarnessCapabilityRecord
) -> Capability:
    """Classify `concurrency_limit` from a rollout-derived ceiling.

    `VERIFIED` needs a refusal, bounds that meet, and a capture from the
    record's pinned version. Otherwise `UNVERIFIED`, with the reason.
    """
    if ceiling is None:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            "No rollout capture shows a spawn refused at the thread limit.",
        )
    bounds = f"between {ceiling.lower_bound} and {ceiling.upper_bound} child threads"
    seen = f"{ceiling.refusals} refused spawn(s) on {ceiling.cli_version} bound the limit {bounds}."
    if not _pinned(record, ceiling.cli_version):
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.BACKEND,
            f"{seen} {_mismatch(record, ceiling.cli_version)}",
            value=None,
        )
    if not ceiling.exact:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.BACKEND, seen)
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"{seen} The bounds meet.",
        value=ceiling.lower_bound,
    )


def classify_context_reset(
    observation: ResetObservation, record: HarnessCapabilityRecord
) -> Capability:
    """Classify `context_reset_observability` from a recorded session.

    Raises `ValueError` when the observation belongs to another harness, which
    is a caller bug and must not read as a capability of this one.
    """
    if observation.harness != record.harness:
        raise ValueError(f"observation is for {observation.harness}, record is {record.harness}")
    if observation.events == 0:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"The {observation.cli_version} capture holds no compaction or truncation event.",
        )
    seen = (
        f"{observation.cli_version} recorded {observation.compactions} compaction(s), "
        f"{observation.failed_compactions} failed, {observation.truncations} truncation(s)."
    )
    if not _pinned(record, observation.cli_version):
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.BACKEND,
            f"{seen} {_mismatch(record, observation.cli_version)}",
        )
    return Capability(CapabilityStatus.VERIFIED, EvidenceKind.BACKEND, seen)
