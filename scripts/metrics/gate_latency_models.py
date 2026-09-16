"""Dataclasses for gate_latency.py's report shape (REQ-027 O2, O4).

Split out so ``scripts/metrics/gate_latency.py`` stays under the project's
500-line taste-lint ceiling, the same reason ``lefthook_summary.py``,
``gate_latency_io.py``, and ``gate_latency_classes.py`` were split out. Pure
data: no subprocess, no file I/O, no parsing. Construction stays in
``gate_latency.py``; serialization stays in ``gate_latency_io.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.metrics.lefthook_summary import JobSample

__all__ = ["GateLatencyReport", "HookRun", "HostProfile", "LatencySummary"]


@dataclass(frozen=True, slots=True)
class HookRun:
    """One whole-hook lefthook invocation (REQ-027 O2 aggregate root).

    Identity: (hook, change_class, repetition_index), held by the caller
    that assembles a list of these; this dataclass carries only the fields
    the ontology assigns to one run.

    ``unknown_status_count`` surfaces, rather than silently absorbs, a
    marker ``lefthook_summary.classify_marker`` cannot classify: a future
    lefthook version or a different terminal could render a status glyph
    outside the family verified this session (see
    ``lefthook_summary.py``'s module docstring), and a nonzero count here
    is the signal that this module's marker sets need a new entry.
    """

    repetition_index: int
    exit_code: int
    wall_clock_seconds: float
    lefthook_reported_seconds: float | None
    jobs_parsed: int
    tree_mutated: bool
    unknown_status_count: int
    samples: list[JobSample]


@dataclass(frozen=True, slots=True)
class LatencySummary:
    """The nearest-rank percentile fold over one scope's samples (REQ-027 O2).

    ``scope`` is a job name or the reserved name ``__hook__`` for the whole
    hook's own wall clock.
    """

    scope: str
    n: int
    p50: float
    p95: float
    min: float
    max: float


@dataclass(frozen=True, slots=True)
class HostProfile:
    """The machine that produced a report's samples."""

    captured_at: str
    cpu_count: int
    platform: str
    python_version: str


@dataclass(frozen=True, slots=True)
class GateLatencyReport:
    """REQ-027's aggregate root: one hook, one change class, N repetitions."""

    commit_sha: str
    captured_at: str
    command: str
    hook: str
    change_class: str
    files: list[str]
    repetitions: int
    host: HostProfile
    runs: list[HookRun]
    summaries: list[LatencySummary]
    declared_budget_seconds: float | None
    percentile_note: str | None
    stdin_ref_line_supplied: bool
    exclusions: list[dict[str, str]]
