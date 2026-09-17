"""Dataclasses for gate_latency.py's report shape (REQ-027 O2, O4).

Split out so ``scripts/metrics/gate_latency.py`` stays under the project's
500-line taste-lint ceiling, the same reason ``lefthook_summary.py``,
``gate_latency_io.py``, and ``gate_latency_classes.py`` were split out. Pure
data: no subprocess, no file I/O, no parsing. Construction stays in
``gate_latency.py``; serialization stays in ``gate_latency_io.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

    ``status`` (added for the D1 fix, epic #5456) classifies whether this
    repetition measured the hook or was cut short: ``"complete"`` (every
    job the hook was going to run, finished or not), ``"truncated"``
    (fewer jobs parsed than the report's other repetitions saw, the
    ``piped: true`` early-exit shape), or ``"timeout"`` (killed by the
    sampler's own subprocess bound). It defaults to ``"complete"`` because
    ``gate_latency_sampler._run_repetition`` cannot classify a single
    repetition in isolation; ``truncated`` is only meaningful relative to
    the other repetitions in the same report, so
    ``gate_latency_sampler.build_report`` reclassifies every run with
    ``dataclasses.replace`` once all repetitions are in hand. See that
    module's docstring for why a report of exactly one repetition can
    never classify a run as ``"truncated"``. ``load_before``/``load_after``
    are the 1-minute load average sampled immediately around this
    repetition's lefthook invocation, or ``None`` where the platform does
    not provide ``os.getloadavg`` (Windows) or the call raised ``OSError``.
    """

    repetition_index: int
    exit_code: int
    wall_clock_seconds: float
    lefthook_reported_seconds: float | None
    jobs_parsed: int
    tree_mutated: bool
    unknown_status_count: int
    samples: list[JobSample]
    status: str = "complete"
    load_before: float | None = None
    load_after: float | None = None


@dataclass(frozen=True, slots=True)
class LatencySummary:
    """The nearest-rank percentile fold over one scope's samples (REQ-027 O2).

    ``scope`` is a job name or the reserved name ``__hook__`` for the whole
    hook's own wall clock.
    """

    scope: str
    is_group: bool
    n: int
    p50: float
    p95: float
    min: float
    max: float


@dataclass(frozen=True, slots=True)
class HostProfile:
    """The machine that produced a report's samples.

    ``load_average`` is ``[1min, 5min, 15min]`` from ``os.getloadavg()``, or
    ``None`` on a platform that does not provide it (Windows) or where the
    call raised ``OSError``. Added for the D2 fix (epic #5456): two latency
    figures taken at unknown and different machine loads are not comparable
    (ci-scripts.md MUST-16), and this is the field that lets a reader tell.
    """

    captured_at: str
    cpu_count: int
    platform: str
    python_version: str
    load_average: list[float] | None = None


@dataclass(frozen=True, slots=True)
class GateLatencyReport:
    """REQ-027's aggregate root: one hook, one change class, N repetitions.

    ``run_status_counts`` maps ``HookRun.status`` to how many repetitions
    landed there (e.g. ``{"complete": 2, "truncated": 1}``), which is what
    makes the D1-fix exclusion in ``gate_latency_stats._build_summaries``
    auditable: a reader can see how many runs were dropped, and why,
    without recomputing it from ``runs``. ``include_incomplete`` records
    whether this report's summaries were built with
    ``--include-incomplete`` (restoring the pre-fix behavior of folding
    every repetition regardless of status); the markdown writer needs this
    to say whether anything was actually excluded.

    ``piped`` is the measured hook's own ``piped:`` flag, read from
    ``lefthook.yml`` (``True``, ``False``, or ``None`` when the config was
    unreadable, the hook was missing, or the key itself was absent).
    ``gate_latency_sampler._classify_run_status`` uses it as the absolute
    truncation signal (D1 follow-up, epic #5456): the relative signal alone
    is blind to truncation that repeats identically across every
    repetition, because the repetition that sets the max job count is
    itself the truncated one. Recorded here so the markdown can say which
    signal was available for a given capture.
    """

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
    hook_args: list[str]
    forced: bool
    exclusions: list[dict[str, str]]
    run_status_counts: dict[str, int] = field(default_factory=dict)
    include_incomplete: bool = False
    piped: bool | None = None
