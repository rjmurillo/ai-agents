"""Percentile folds over gate_latency.py's samples (REQ-027 O2: LatencySummary).

Split out to keep ``scripts/metrics/gate_latency.py`` under the project's
500-line taste-lint ceiling, the same reason the parser, the io writers, the
models, and the change-class table are their own modules. Raising the
ratchet baseline instead is forbidden by ci-scripts.md MUST NOT item 4.

These are pure functions over sample lists: no subprocess, no filesystem, no
clock. That is what makes the percentile arithmetic testable against
hand-computed expectations rather than against a hook run.
"""

from __future__ import annotations

from collections import defaultdict
from math import ceil

from scripts.metrics.gate_latency_models import HookRun, LatencySummary


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    """Nearest-rank percentile, 1-indexed.

    ``sorted_values[max(0, ceil(p / 100 * n) - 1)]``. Hand-verified: for
    ``[1, 2, 3, 4, 5]``, p50 is 3 and p95 is 5; for ``n == 1``, every
    percentile is that one value.
    """
    if not values:
        raise ValueError("cannot compute a percentile of an empty sample")
    ordered = sorted(values)
    n = len(ordered)
    rank = max(0, ceil(percentile / 100 * n) - 1)
    return ordered[rank]


def _percentile_note(n: int) -> str | None:
    """State p95's status as an upper-order statistic when ``n`` is below 20 (AC-05)."""
    if n >= 20:
        return None
    return (
        f"n={n} is below 20: p95 in this report is an upper-order statistic "
        "of the observed samples, not a tail estimate."
    )


def _smallest_scope_n(summaries: list[LatencySummary], fallback: int) -> int:
    """The smallest per-scope sample count, which is what AC-05's threshold reads.

    Keying the note off ``repetitions`` alone would miss the case that
    matters: a hook that aborts part-way leaves a late job with fewer
    samples than the run count, so a 20-repetition report could carry a
    p95 for a job observed three times with no note attached.
    """
    return min((summary.n for summary in summaries), default=fallback)


def _build_summaries(
    runs: list[HookRun], include_incomplete: bool = False
) -> list[LatencySummary]:
    """Fold every run's samples into one ``LatencySummary`` per scope.

    ``__hook__`` is scored on the sampler's own ``wall_clock_seconds``
    (AC-03: the end-to-end clock, kept separate from lefthook's
    self-reported total, which is recorded per run but not itself
    summarized). Sorting is alphabetical, which places ``__hook__`` first
    (``_`` sorts before any letter).

    D1 fix (epic #5456): with ``include_incomplete=False`` (the default),
    a run whose ``status`` is not ``"complete"`` contributes nothing to any
    scope. Before this fix, every repetition's ``wall_clock_seconds``
    folded into ``__hook__`` regardless of whether the hook ran every job
    it was going to run; a ``piped: true`` pre-push hook that aborted early
    on a failed job produced a short wall clock indistinguishable from a
    legitimately fast run, biasing p50/p95 downward exactly when the
    machine was too loaded to finish. ``include_incomplete=True`` restores
    that pre-fix behavior (wired to ``--include-incomplete`` in
    ``gate_latency.py``) for a caller who wants the raw, unfiltered
    numbers. When no run is ``"complete"`` and ``include_incomplete`` is
    left off, ``by_scope`` stays empty and this returns ``[]`` rather than
    fabricating a figure from data that never measured a full hook run.
    """
    eligible = runs if include_incomplete else [run for run in runs if run.status == "complete"]
    by_scope: dict[str, list[float]] = defaultdict(list)
    groups: set[str] = set()
    for run in eligible:
        by_scope["__hook__"].append(run.wall_clock_seconds)
        for sample in run.samples:
            by_scope[sample.name].append(sample.seconds)
            if sample.is_group:
                groups.add(sample.name)
    return [
        LatencySummary(
            scope=scope,
            is_group=scope in groups,
            n=len(values),
            p50=_nearest_rank_percentile(values, 50),
            p95=_nearest_rank_percentile(values, 95),
            min=min(values),
            max=max(values),
        )
        for scope, values in sorted(by_scope.items())
    ]
