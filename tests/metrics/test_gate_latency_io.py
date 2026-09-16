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
import os
import stat
import sys
from pathlib import Path

import pytest

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
    summary_hook = LatencySummary(scope="__hook__", n=n, p50=0.6, p95=0.7, min=0.6, max=0.7)
    summary_job = LatencySummary(scope="a-job", n=n, p50=0.5, p95=0.55, min=0.5, max=0.55)
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
    assert report.percentile_note in text


def test_edge_write_markdown_omits_percentile_note_when_absent(tmp_path: Path) -> None:
    report = _sample_report()
    report_no_note = dataclasses.replace(report, percentile_note=None)
    path = tmp_path / "out.md"
    gl_io.write_markdown(report_no_note, path)
    text = path.read_text(encoding="utf-8")
    assert "upper-order statistic" not in text


# --- Owner-only mode (CWE-276) ------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits; os.fchmod is POSIX-only")
def test_edge_write_json_permission_mode_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "mode.json"
    gl_io.write_json(_sample_report(), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# --- Symlink-refusing writer (CWE-59) ----------------------------------------


def test_negative_safe_open_refuses_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(gl_io.SymlinkRefusedError):
        gl_io.safe_open(link)


def test_negative_write_json_refuses_symlink_target(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(gl_io.SymlinkRefusedError):
        gl_io.write_json(_sample_report(), link)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits; os.fchmod is POSIX-only")
def test_negative_safe_open_narrows_preexisting_broader_mode(tmp_path: Path) -> None:
    target = tmp_path / "existing.json"
    target.write_text("stale\n", encoding="utf-8")
    target.chmod(0o644)
    fd = gl_io.safe_open(target)
    try:
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    finally:
        os.close(fd)


# --- AC-05 headline framing, and the stdin provenance line -------------------


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
    thin = LatencySummary(scope="late-job", n=2, p50=1.0, p95=1.2, min=1.0, max=1.2)
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
