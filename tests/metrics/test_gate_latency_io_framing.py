"""How the markdown presents a figure the sample size does or does not support.

AC-05: below n=20 the table offers no column labelled p95 and leads with the
worst observed run instead, because the label is what gets quoted once a
number leaves the artifact. Also pins the provenance line that distinguishes a
faithful capture from a bare one.

Split from test_gate_latency_io.py for the cohesion reason recorded in
test_gate_latency_io_safety.py.
"""

from __future__ import annotations

import dataclasses

from scripts.metrics import gate_latency_io as gl_io
from scripts.metrics.gate_latency_models import (
    GateLatencyReport,
    HookRun,
    HostProfile,
    LatencySummary,
)
from scripts.metrics.lefthook_summary import JobSample


def _sample_report(*, n: int = 1, stdin_supplied: bool = False) -> GateLatencyReport:
    sample = JobSample(name="a-job", seconds=0.5, status="pass", marker="✓", depth=0)
    run = HookRun(
        repetition_index=0,
        exit_code=0,
        wall_clock_seconds=0.6,
        lefthook_reported_seconds=0.5,
        jobs_parsed=1,
        tree_mutated=False,
        unknown_status_count=0,
        samples=[sample],
    )
    host = HostProfile(
        captured_at="2026-01-01T00:00:00+00:00",
        cpu_count=4,
        platform="test-platform",
        python_version="3.14.0",
    )
    summary_hook = LatencySummary(
        scope="__hook__", is_group=False, n=n, p50=0.6, p95=0.7, min=0.6, max=0.7
    )
    summary_job = LatencySummary(
        scope="a-job", is_group=False, n=n, p50=0.5, p95=0.55, min=0.5, max=0.55
    )
    return GateLatencyReport(
        commit_sha="deadbeef",
        captured_at="2026-01-01T00:00:00+00:00",
        command="scripts/metrics/gate_latency.py --hook pre-commit",
        hook="pre-commit",
        change_class="none",
        files=[],
        repetitions=1,
        host=host,
        runs=[run],
        summaries=[summary_hook, summary_job],
        declared_budget_seconds=120.0,
        percentile_note=(
            f"n={n} is below 20: p95 in this report is an upper-order statistic "
            "of the observed samples, not a tail estimate."
            if n < 20
            else None
        ),
        stdin_ref_line_supplied=stdin_supplied,
        hook_args=[],
        forced=False,
        exclusions=[],
    )


# --- AC-05 headline framing and the provenance line --------------------------

def test_positive_markdown_headlines_worst_observed_below_the_threshold(tmp_path):
    """Below n=20 the table offers no p95 column, only the worst observed run (AC-05)."""
    path = tmp_path / "low-n.md"
    gl_io.write_markdown(_sample_report(n=3), path)

    body = path.read_text(encoding="utf-8")

    assert "worst observed of n runs" in body
    assert "| p95 " not in body
    assert "p95 in this report is an upper-order statistic" in body


def test_positive_markdown_reports_p95_at_or_above_the_threshold(tmp_path):
    """At n=20 the percentile is supportable, so the table names it (AC-05)."""
    path = tmp_path / "high-n.md"
    gl_io.write_markdown(_sample_report(n=20), path)

    body = path.read_text(encoding="utf-8")

    assert "| p95 " in body
    assert "worst observed of n runs" not in body


def test_edge_markdown_uses_low_n_shape_when_any_single_scope_is_below_threshold(tmp_path):
    """One under-sampled scope downgrades the whole table, never just its own row."""
    report = _sample_report(n=20)
    thin = LatencySummary(scope="late-job", is_group=False, n=2, p50=1.0, p95=1.2, min=1.0, max=1.2)
    report = dataclasses.replace(report, summaries=[*report.summaries, thin])
    path = tmp_path / "mixed-n.md"

    gl_io.write_markdown(report, path)

    body = path.read_text(encoding="utf-8")
    assert "worst observed of n runs" in body
    assert "| p95 " not in body


def test_positive_markdown_records_whether_a_stdin_ref_line_was_supplied(tmp_path):
    """A faithful capture must be distinguishable from a bare one in the artifact."""
    supplied = tmp_path / "supplied.md"
    bare = tmp_path / "bare.md"

    gl_io.write_markdown(_sample_report(stdin_supplied=True), supplied)
    gl_io.write_markdown(_sample_report(stdin_supplied=False), bare)

    assert "Stdin ref line supplied: True" in supplied.read_text(encoding="utf-8")
    assert "Stdin ref line supplied: False" in bare.read_text(encoding="utf-8")
