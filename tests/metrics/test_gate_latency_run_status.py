"""Run-completeness classification: complete, truncated, timeout (REQ-027 D1 fix).

D1 (the defect brief's own name): a truncated repetition's wall clock used to
fold into ``__hook__`` indistinguishably from a fast run, because
``_build_summaries`` had no check on ``HookRun.exit_code`` or job count. A
``piped: true`` pre-push hook that aborts early on a loaded machine produced
exactly this shape, biasing p50/p95 downward when the machine was too
contended to finish, which inverted the signal the sampler exists to report.

``_classify_run_status`` (``gate_latency_sampler.py``) and the status filter
in ``_build_summaries`` (``gate_latency_stats.py``) are what this module pins
at the unit level: constructed ``HookRun``s, no subprocess and no clock. The
end-to-end ``build_report``/CLI coverage and the markdown ``_exclusion_sentence``
coverage live in ``test_gate_latency_run_status_cli.py``, split out for the
same file-size reason the sibling ``test_gate_latency_*`` modules document in
their own docstrings.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from scripts.metrics import gate_latency_sampler as gls_sampler
from scripts.metrics import gate_latency_stats as gls_stats
from scripts.metrics.gate_latency_models import GateLatencyReport, HookRun, HostProfile

_BASE_RUN = HookRun(
    repetition_index=0,
    exit_code=0,
    wall_clock_seconds=1.0,
    lefthook_reported_seconds=1.0,
    jobs_parsed=1,
    tree_mutated=False,
    unknown_status_count=0,
    samples=[],
    status="complete",
)


def _run(**overrides: Any) -> HookRun:
    """A minimal, already-classified ``"complete"`` ``HookRun``.

    Each test overrides only the fields it varies, so the fields that do
    not matter to a given assertion stay out of that test's body. Typed
    ``Any`` rather than a narrower union because ``dataclasses.replace``'s
    stub checks each keyword against its field's own type, and this helper
    fans out over every field ``HookRun`` has.
    """
    return dataclasses.replace(_BASE_RUN, **overrides)


# --- _classify_run_status (unit) ----------------------------------------------


def test_positive_full_job_set_nonzero_exit_is_complete() -> None:
    """A run that FAILED a gate but ran every job measured the hook (D1's own framing)."""
    run = _run(exit_code=1, jobs_parsed=3)
    assert gls_sampler._classify_run_status(run, max_jobs_parsed=3) == "complete"


def test_negative_fewer_jobs_than_the_report_max_is_truncated() -> None:
    run = _run(exit_code=1, jobs_parsed=1)
    assert gls_sampler._classify_run_status(run, max_jobs_parsed=3) == "truncated"


def test_negative_timeout_exit_code_wins_even_with_a_full_job_count() -> None:
    """``exit_code`` alone decides timeout; ``jobs_parsed`` is irrelevant once it fires."""
    run = _run(exit_code=gls_sampler._TIMEOUT_EXIT_CODE, jobs_parsed=3)
    assert gls_sampler._classify_run_status(run, max_jobs_parsed=3) == "timeout"


def test_edge_single_repetition_cannot_be_classified_truncated() -> None:
    """n=1: the run's own count IS the max, so it reads complete (documented limitation)."""
    run = _run(exit_code=1, jobs_parsed=1)
    assert gls_sampler._classify_run_status(run, max_jobs_parsed=1) == "complete"


def test_positive_exact_zero_jobs_parsed_equal_to_the_max_is_complete() -> None:
    """A hook with no jobs at all (max=0) must not read as truncated against itself."""
    run = _run(exit_code=0, jobs_parsed=0)
    assert gls_sampler._classify_run_status(run, max_jobs_parsed=0) == "complete"


# --- _build_summaries excludes non-complete runs (D1 regression) -------------


def test_negative_a_truncated_repetitions_wall_clock_is_absent_from_hook_summary() -> None:
    """Fails against the pre-fix ``_build_summaries``, which had no status check.

    Before the fix, every repetition's ``wall_clock_seconds`` folded into
    ``__hook__`` regardless of ``exit_code`` or job count. Here the
    truncated run's 2.0s would pull the summary down to n=2, min=2.0 if it
    leaked in; the fix keeps it out entirely.
    """
    complete = _run(
        repetition_index=0, wall_clock_seconds=100.0, jobs_parsed=3, status="complete"
    )
    truncated = _run(
        repetition_index=1,
        exit_code=1,
        wall_clock_seconds=2.0,
        jobs_parsed=1,
        status="truncated",
    )

    summaries = gls_stats._build_summaries([complete, truncated])

    hook_summary = next(s for s in summaries if s.scope == "__hook__")
    assert hook_summary.n == 1
    assert hook_summary.min == 100.0
    assert hook_summary.max == 100.0


def test_positive_a_complete_nonzero_exit_run_is_included() -> None:
    """The D1 fix must not exclude a run for the reason it FAILED a gate."""
    failed_but_complete = _run(
        exit_code=1, wall_clock_seconds=5.0, jobs_parsed=2, status="complete"
    )
    passed = _run(exit_code=0, wall_clock_seconds=6.0, jobs_parsed=2, status="complete")

    summaries = gls_stats._build_summaries([failed_but_complete, passed])

    hook_summary = next(s for s in summaries if s.scope == "__hook__")
    assert hook_summary.n == 2


def test_negative_a_timeout_run_is_excluded() -> None:
    timed_out = _run(
        exit_code=gls_sampler._TIMEOUT_EXIT_CODE, wall_clock_seconds=3600.0, status="timeout"
    )
    complete = _run(wall_clock_seconds=10.0, status="complete")

    summaries = gls_stats._build_summaries([timed_out, complete])

    hook_summary = next(s for s in summaries if s.scope == "__hook__")
    assert hook_summary.n == 1
    assert hook_summary.max == 10.0


def test_edge_every_run_incomplete_yields_empty_summaries() -> None:
    """No run classified 'complete': summaries must be empty, never fabricated."""
    runs = [
        _run(repetition_index=0, status="truncated"),
        _run(
            repetition_index=1,
            status="timeout",
            exit_code=gls_sampler._TIMEOUT_EXIT_CODE,
        ),
    ]

    assert gls_stats._build_summaries(runs) == []


def test_positive_include_incomplete_restores_every_run() -> None:
    complete = _run(
        repetition_index=0, wall_clock_seconds=100.0, jobs_parsed=3, status="complete"
    )
    truncated = _run(
        repetition_index=1,
        exit_code=1,
        wall_clock_seconds=2.0,
        jobs_parsed=1,
        status="truncated",
    )

    summaries = gls_stats._build_summaries([complete, truncated], include_incomplete=True)

    hook_summary = next(s for s in summaries if s.scope == "__hook__")
    assert hook_summary.n == 2
    assert hook_summary.min == 2.0


# --- Backward compatibility: pre-existing kwargs alone still construct -------


def test_positive_hookrun_constructs_with_only_pre_existing_kwargs() -> None:
    run = HookRun(
        repetition_index=0,
        exit_code=0,
        wall_clock_seconds=1.0,
        lefthook_reported_seconds=1.0,
        jobs_parsed=1,
        tree_mutated=False,
        unknown_status_count=0,
        samples=[],
    )
    assert run.status == "complete"
    assert run.load_before is None
    assert run.load_after is None


def test_positive_hostprofile_constructs_with_only_pre_existing_kwargs() -> None:
    host = HostProfile(
        captured_at="2026-01-01T00:00:00+00:00",
        cpu_count=4,
        platform="test",
        python_version="3.14.0",
    )
    assert host.load_average is None


def test_positive_gatelatencyreport_constructs_with_only_pre_existing_kwargs() -> None:
    host = HostProfile(
        captured_at="2026-01-01T00:00:00+00:00",
        cpu_count=4,
        platform="t",
        python_version="3.14.0",
    )
    run = HookRun(
        repetition_index=0,
        exit_code=0,
        wall_clock_seconds=1.0,
        lefthook_reported_seconds=1.0,
        jobs_parsed=1,
        tree_mutated=False,
        unknown_status_count=0,
        samples=[],
    )
    report = GateLatencyReport(
        commit_sha="deadbeef",
        captured_at="2026-01-01T00:00:00+00:00",
        command="cmd",
        hook="pre-commit",
        change_class="none",
        files=[],
        repetitions=1,
        host=host,
        runs=[run],
        summaries=[],
        declared_budget_seconds=None,
        percentile_note=None,
        stdin_ref_line_supplied=False,
        hook_args=[],
        forced=False,
        exclusions=[],
    )
    assert report.run_status_counts == {}
    assert report.include_incomplete is False
