"""Filesystem safety of the report writers (CWE-59, CWE-276).

The writers open with O_NOFOLLOW at mode 0600, so a symlinked target is
refused rather than followed and a pre-existing broader mode is narrowed. Both
matter because the sampler writes into a repository tree that other processes
share.

Split from test_gate_latency_io.py, which held this alongside the writers'
output shape and the AC-05 headline framing.
"""

from __future__ import annotations

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


# --- Owner-only mode and the symlink-refusing writer -------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits; os.fchmod is POSIX-only")
def test_edge_write_json_permission_mode_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "mode.json"
    gl_io.write_json(_sample_report(), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


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

