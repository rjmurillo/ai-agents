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
`BACKEND` class `EvidenceKind` names ("runtime event stream"). The one value the
operator supplies, `configured_max_threads`, can only withhold `VERIFIED`: it
grants nothing unless the recorded peak of running children equals it.

Stricter/looser/different than canonical: `apply_behavioral_probe` in
`_harness_capability.py` upgrades a cell from a live probe result. These
classifiers upgrade from a file a past run left behind, so the cell's date is the
capture's, not today's. `_recorded_captures.apply_verified` adds the sources and
the command that regenerates the cell.
"""

from __future__ import annotations

import re
from functools import partial

from _codex_rollout import NoCeiling, SpawnCeiling
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


_NO_CEILING_DETAIL = {
    NoCeiling.NO_REFUSAL: "No rollout capture shows a spawn refused at the thread limit.",
    NoCeiling.FOREIGN_PARENT: "A child rollout names a different parent, so no ceiling is read.",
    NoCeiling.MIXED_VERSIONS: (
        "The parent and a child ran different CLI versions, so no ceiling is read."
    ),
    NoCeiling.UNPAIRED_TURNS: (
        "The parent refused spawns, but a child's turns do not pair up (a child ended in "
        "turn_aborted when the parent finished without waiting), so the peak of running "
        "children is unmeasurable and no ceiling is read. The parent must wait for its children."
    ),
    NoCeiling.NO_CHILD_TURNS: "No child rollout ran a turn, so no ceiling is read.",
    NoCeiling.INCONSISTENT_BOUNDS: (
        "The refusals came before as many children as ran at once, so the bounds are "
        "inconsistent and no ceiling is read."
    ),
}


def classify_spawn_ceiling(
    ceiling: SpawnCeiling | NoCeiling,
    record: HarnessCapabilityRecord,
    configured_max_threads: int | None = None,
) -> Capability:
    """Classify `concurrency_limit` from a rollout-derived ceiling.

    The limit is a per-invocation setting (`-c agents.max_threads=N`), so a
    capture proves only what that session's cap did. `VERIFIED` therefore needs
    all of: a refused spawn, a capture from the record's pinned version, the
    operator stating the configured value, and a peak of running children equal
    to it. Then the runtime admitted exactly that many and refused one more,
    which is enforcement observed rather than echoed. Anything else is
    `UNVERIFIED`, with the reason. The rollout's upper bound never decides.
    """
    if isinstance(ceiling, NoCeiling):
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            _NO_CEILING_DETAIL[ceiling],
        )
    bounds = f"between {ceiling.lower_bound} and {ceiling.upper_bound} child threads"
    seen = f"{ceiling.refusals} refused spawn(s) on {ceiling.cli_version} bound the limit {bounds}."
    unverified = partial(Capability, CapabilityStatus.UNVERIFIED, EvidenceKind.BACKEND)
    if not _pinned(record, ceiling.cli_version):
        return unverified(f"{seen} {_mismatch(record, ceiling.cli_version)}")
    if configured_max_threads is None:
        return unverified(
            f"{seen} The session's agents.max_threads is not recorded, so this is that "
            "session's cap and not evidence of the runtime's limit."
        )
    if ceiling.lower_bound != configured_max_threads:
        return unverified(
            f"{seen} The session configured agents.max_threads={configured_max_threads}, "
            f"but {ceiling.lower_bound} children ran at once."
        )
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"With agents.max_threads={configured_max_threads}, {ceiling.lower_bound} children "
        f"ran at once and {ceiling.refusals} further spawn(s) were refused.",
        value=configured_max_threads,
        date=ceiling.captured_on,
    )


def classify_context_reset(
    observation: ResetObservation, record: HarnessCapabilityRecord
) -> Capability:
    """Classify `context_reset_observability` from a recorded session.

    Raises `ValueError` when the observation belongs to another harness, which
    is a caller bug and must not read as a capability of this one. A failed
    compaction alone does not verify: it changed nothing the harness could
    later be observed to have reset.
    """
    if observation.harness != record.harness:
        raise ValueError(f"observation is for {observation.harness}, record is {record.harness}")
    if observation.resets == 0:
        attempts = (
            f" {observation.failed_compactions} compaction attempt(s) failed."
            if observation.failed_compactions
            else ""
        )
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"The {observation.cli_version} capture holds no successful compaction or "
            f"truncation.{attempts}",
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
    return Capability(
        CapabilityStatus.VERIFIED, EvidenceKind.BACKEND, seen, date=observation.captured_on
    )
