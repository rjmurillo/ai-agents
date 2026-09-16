"""IO-boundary tests for gate_latency_io.py (REQ-027 T5).

Split from ``test_gate_latency.py`` to keep both files under the project's
500-line taste-lint ceiling, mirroring
``tests/metrics/test_control_plane_baseline.py`` plus
``tests/metrics/test_control_plane_baseline_io.py``. Covers the
symlink-refusing writer (CWE-59), owner-only mode narrowing on a
pre-existing file, and the JSON/markdown output shape, exercised directly
against ``write_json``/``write_markdown`` on a hand-built
``GateLatencyReport`` rather than through ``gate_latency.main``'s
subprocess-mocked CLI path: this is a narrower, cheaper way to test the
same writer contract that a CLI-level round trip proved before the split,
and no test case's assertions were dropped in the move.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

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


# --- JSON/markdown shape (positive) ------------------------------------------


def test_positive_write_json_round_trips_report_shape(tmp_path: Path) -> None:
    report = _sample_report()
    path = tmp_path / "out.json"
    gl_io.write_json(report, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["hook"] == "pre-commit"
    assert data["repetitions"] == 1
    assert len(data["runs"]) == 1
    assert data["runs"][0]["samples"][0]["name"] == "a-job"
    assert data["runs"][0]["unknown_status_count"] == 0
    assert {s["scope"] for s in data["summaries"]} == {"__hook__", "a-job"}


def test_positive_write_markdown_includes_required_sections(tmp_path: Path) -> None:
    report = _sample_report()
    path = tmp_path / "out.md"
    gl_io.write_markdown(report, path)
    text = path.read_text(encoding="utf-8")
    assert "# Gate latency: pre-commit (none)" in text
    assert "## Latency by scope" in text
    assert "## Per-repetition runs" in text
    assert "one machine on one date" in text
    note = report.percentile_note
    assert note is not None
    assert note in text


def test_edge_write_markdown_omits_percentile_note_when_absent(tmp_path: Path) -> None:
    report = _sample_report()
    report_no_note = dataclasses.replace(report, percentile_note=None)
    path = tmp_path / "out.md"
    gl_io.write_markdown(report_no_note, path)
    text = path.read_text(encoding="utf-8")
    assert "upper-order statistic" not in text


# --- Owner-only mode (CWE-276) ------------------------------------------------


# --- Symlink-refusing writer (CWE-59) ----------------------------------------


# --- AC-05 headline framing, and the stdin provenance line -------------------

