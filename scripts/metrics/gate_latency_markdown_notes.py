"""Prose lines ``gate_latency_io.write_markdown`` composes into the report body.

Split from ``scripts/metrics/gate_latency_io.py`` to keep that module under
the project's 300-line taste-lint warning ceiling, the same reason
``lefthook_summary.py``, ``gate_latency_probe.py``, ``gate_latency_stats.py``,
``gate_latency_classes.py``, and ``gate_latency_classify.py`` are their own
modules (see each one's docstring). Pure string composition over an
already-built ``GateLatencyReport``: no subprocess, no file I/O, no clock.
``write_markdown`` still owns the file write and the line ordering; this
module only supplies the sentences.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.metrics.gate_latency_models import GateLatencyReport, HostProfile


def _status_counts(report: GateLatencyReport) -> dict[str, int]:
    """``report.run_status_counts``, or derived from ``report.runs`` when absent.

    ``build_report`` always populates ``run_status_counts``; the fallback is
    for a ``GateLatencyReport`` built directly (as several test fixtures do,
    predating this field), so the markdown still reflects the runs it was
    actually given rather than reading as if none were run.
    """
    if report.run_status_counts:
        return report.run_status_counts
    counts: dict[str, int] = {}
    for run in report.runs:
        counts[run.status] = counts.get(run.status, 0) + 1
    return counts


def _exclusion_sentence(report: GateLatencyReport) -> list[str]:
    """State how many repetitions the summaries above exclude, and why (REQ-027 D1 fix).

    Read this alongside ``gate_latency_io._run_table``: the ``status``
    column there is the row-by-row evidence for the aggregate count this
    sentence reports.
    """
    counts = _status_counts(report)
    total = sum(counts.values())
    complete = counts.get("complete", 0)
    if total == 0:
        return ["No repetitions were run."]
    if report.include_incomplete:
        return [
            f"`--include-incomplete` was set: the summaries below fold in all {total} "
            "repetitions regardless of status."
        ]
    if complete == total:
        return [f"The summaries below cover all {total} repetitions."]
    reasons = ", ".join(
        f"{count} {status}" for status, count in sorted(counts.items()) if status != "complete"
    )
    if complete == 0:
        return [
            f"**No latency figure is reported.** All {total} repetitions were excluded "
            f"from the summaries below because none reached status `complete` ({reasons}); "
            "see the per-repetition table for which repetition was which (REQ-027 D1)."
        ]
    return [
        f"{total - complete} of {total} repetitions were excluded from the summaries "
        f"below because they did not measure the whole hook ({reasons}); see the "
        "per-repetition table for which repetition was which (REQ-027 D1)."
    ]


def _load_line(host: HostProfile) -> str:
    """Load average and load-per-CPU, or an explicit unavailability note (REQ-027 D2).

    Load-per-CPU (the 1-minute figure divided by ``cpu_count``) is what
    makes two machines with different core counts comparable; a raw load
    average alone is not. See ci-scripts.md MUST-16: a standalone run does
    not predict cost on a loaded machine, and this is the telemetry that
    lets a reader tell whether the machine was loaded when a figure below
    was captured.
    """
    if host.load_average is None:
        return "not available on this platform"
    one_min, five_min, fifteen_min = host.load_average
    per_cpu = one_min / host.cpu_count if host.cpu_count else one_min
    return (
        f"{one_min:.2f}, {five_min:.2f}, {fifteen_min:.2f} (1/5/15 min); "
        f"{per_cpu:.2f} per CPU"
    )


def _piped_line(report: GateLatencyReport) -> str:
    """State which truncation trigger applied to this capture (REQ-027 D1 follow-up).

    ``_classify_run_status`` (``gate_latency_classify.py``) has two
    independent truncation triggers, and this is where a reader learns
    which one was available. The piped-true branch names the trigger's
    deliberate conservative false positive explicitly, because that is the
    one direction this instrument accepts being wrong in: a piped hook
    whose LAST job fails ran every job and did measure the whole hook, and
    is still classified ``truncated`` rather than risk reporting a figure
    that did not measure a full run (the D1 defect this whole mechanism
    exists to prevent).
    """
    if report.piped is None:
        return (
            "Hook `piped` flag: unknown (`lefthook.yml` unreadable, missing this "
            "hook, or no `piped` key on it). The absolute truncation check is "
            "disabled for this capture; classification used the relative check "
            "alone."
        )
    if report.piped:
        return (
            "Hook `piped` flag: true. A non-zero exit is treated as truncation "
            "(lefthook's piped semantics: a failed job skips the remainder), "
            "even at n=1. This is a deliberate conservative false positive: a "
            "piped hook whose LAST job fails ran every job and is still "
            "classified `truncated`, because excluding one valid sample costs "
            "less than including one invalid one."
        )
    return (
        "Hook `piped` flag: false. Only the relative truncation check applies "
        "(fewer jobs parsed than another repetition in this report)."
    )
