"""Tests for the workflow-debounce action script (ADR-006 extraction, #2967).

Locks the behavior extracted from `.github/actions/workflow-debounce/action.yml`:
the step outputs (start/end/duration), the job-summary markdown, and the
exit-code contract. The sleep and clock are injected so the timing math is
deterministic, and the GitHub output/summary files are redirected to tmp
paths.

Without these tests a future edit to the debounce script could silently change
the `duration` output or the summary format that the composite action's
declared outputs depend on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "actions" / "workflow-debounce" / "debounce.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("debounce", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


debounce = _load()


# --- pure helpers ----------------------------------------------------------


def test_iso_utc_formats_second_precision() -> None:
    # 2021-01-01T00:00:00Z is epoch 1609459200.
    assert debounce.iso_utc(1609459200) == "2021-01-01T00:00:00Z"


def test_build_output_lines_shape() -> None:
    lines = debounce.build_output_lines("S", "E", 10)
    assert lines == ["start=S", "end=E", "duration=10"]


def test_build_summary_contains_all_rows() -> None:
    summary = debounce.build_summary("WF", "grp", "10", 12, "S", "E")
    assert "## Workflow Debouncing Applied" in summary
    assert "| **Workflow** | WF |" in summary
    assert "| **Concurrency Group** | grp |" in summary
    assert "| **Delay Configured** | 10s |" in summary
    assert "| **Actual Duration** | 12s |" in summary
    assert "| **Start Time** | S |" in summary
    assert "| **End Time** | E |" in summary


# --- run(): positive -------------------------------------------------------


def test_run_writes_outputs_and_summary(tmp_path: Path) -> None:
    out = tmp_path / "output"
    summary = tmp_path / "summary"
    slept: list[float] = []
    # clock returns start then end: a 7-second window.
    ticks = iter([1609459200.0, 1609459207.0])
    env = {
        "DELAY_SECONDS": "7",
        "WORKFLOW_NAME": "AI Spec Validation",
        "CONCURRENCY_GROUP": "ai-spec-42",
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
    }

    rc = debounce.run(env, sleep=slept.append, clock=lambda: next(ticks))

    assert rc == 0
    assert slept == [7]
    out_text = out.read_text(encoding="utf-8")
    assert "start=2021-01-01T00:00:00Z" in out_text
    assert "end=2021-01-01T00:00:07Z" in out_text
    assert "duration=7" in out_text
    summary_text = summary.read_text(encoding="utf-8")
    assert "| **Actual Duration** | 7s |" in summary_text
    assert "| **Delay Configured** | 7s |" in summary_text


def test_run_defaults_delay_to_ten(tmp_path: Path) -> None:
    out = tmp_path / "output"
    slept: list[float] = []
    ticks = iter([100.0, 110.0])
    rc = debounce.run(
        {"GITHUB_OUTPUT": str(out)},
        sleep=slept.append,
        clock=lambda: next(ticks),
    )
    assert rc == 0
    assert slept == [10]


# --- run(): negative / edge -----------------------------------------------


def test_run_rejects_non_numeric_delay(capsys: pytest.CaptureFixture[str]) -> None:
    rc = debounce.run({"DELAY_SECONDS": "soon"}, sleep=lambda _s: None)
    assert rc == 1
    assert "DELAY_SECONDS must be a number" in capsys.readouterr().err


def test_run_accepts_fractional_delay(tmp_path: Path) -> None:
    # The old bash `sleep "$DELAY_SECONDS"` accepted fractional seconds; preserve
    # that contract (float parse), so "0.5" sleeps 0.5s rather than erroring.
    out = tmp_path / "output"
    slept: list[float] = []
    ticks = iter([0.0, 0.5])
    rc = debounce.run(
        {"DELAY_SECONDS": "0.5", "GITHUB_OUTPUT": str(out)},
        sleep=slept.append,
        clock=lambda: next(ticks),
    )
    assert rc == 0
    assert slept == [0.5]


def test_run_rejects_negative_delay(capsys: pytest.CaptureFixture[str]) -> None:
    slept: list[float] = []
    rc = debounce.run({"DELAY_SECONDS": "-5"}, sleep=slept.append)
    assert rc == 1
    assert "DELAY_SECONDS must be non-negative" in capsys.readouterr().err
    # Rejected before sleeping (a negative sleep would otherwise raise).
    assert slept == []


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "Infinity"])
def test_run_rejects_non_finite_delay(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # float() accepts nan/inf/-inf; sleep(nan) raises and sleep(inf) would hang
    # the job forever, so they must be rejected before sleeping.
    slept: list[float] = []
    rc = debounce.run({"DELAY_SECONDS": value}, sleep=slept.append)
    assert rc == 1
    assert "DELAY_SECONDS must be finite" in capsys.readouterr().err
    assert slept == []


def test_run_without_github_files_does_not_crash() -> None:
    # No GITHUB_OUTPUT / GITHUB_STEP_SUMMARY in env: the appends are skipped.
    ticks = iter([0.0, 3.0])
    rc = debounce.run({"DELAY_SECONDS": "3"}, sleep=lambda _s: None, clock=lambda: next(ticks))
    assert rc == 0


def test_run_truncates_fractional_duration(tmp_path: Path) -> None:
    # Matches the old `date +%s` contract: floor both timestamps, then subtract.
    # int(9.6) - int(0.0) == 9 (not 10 from rounding the 9.6s delta).
    out = tmp_path / "output"
    ticks = iter([0.0, 9.6])
    debounce.run(
        {"DELAY_SECONDS": "10", "GITHUB_OUTPUT": str(out)},
        sleep=lambda _s: None,
        clock=lambda: next(ticks),
    )
    assert "duration=9" in out.read_text(encoding="utf-8")


def test_run_duration_floors_both_endpoints(tmp_path: Path) -> None:
    # Fractional start and end: int(10.1) - int(0.9) == 10 - 0 == 10, the same
    # value the two `date +%s` calls would have produced.
    out = tmp_path / "output"
    ticks = iter([0.9, 10.1])
    debounce.run(
        {"DELAY_SECONDS": "10", "GITHUB_OUTPUT": str(out)},
        sleep=lambda _s: None,
        clock=lambda: next(ticks),
    )
    assert "duration=10" in out.read_text(encoding="utf-8")
