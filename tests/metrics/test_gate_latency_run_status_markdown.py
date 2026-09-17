"""CLI-driven markdown/JSON rendering for run status, and ``_exclusion_sentence`` (REQ-027 D1).

Split from ``test_gate_latency_run_status_cli.py``, which holds the
``build_report``-level classification coverage; splitting keeps both files
well under the project's 500-line taste-lint ceiling, the same reason the
other ``test_gate_latency_*`` modules document their own splits.

``subprocess.run`` is monkeypatched throughout; no test here runs a real
lefthook hook. ``_exclusion_sentence`` (``gate_latency_markdown_notes.py``,
re-exported through ``gate_latency_io``) is exercised directly at the unit
level in this module's last section, since it renders the same
``run_status_counts``/``include_incomplete`` fields the CLI tests above it
drive end to end.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import gate_latency as gl
from scripts.metrics import gate_latency_io as gl_io
from scripts.metrics.gate_latency_models import GateLatencyReport, HostProfile


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


_TWO_JOB_STDOUT = (
    "summary: (done in 0.30 seconds)\n✓ job-a (0.10 seconds)\n✓ job-b (0.20 seconds)\n"
)
_ONE_JOB_STDOUT = "summary: (done in 0.10 seconds)\n✓ job-a (0.10 seconds)\n"

_HookResponse = _FakeCompleted | Callable[[list[str]], _FakeCompleted]


def _git_aware(hook_response: _HookResponse) -> Callable[..., _FakeCompleted]:
    """A ``subprocess.run`` fake: git calls succeed; everything else is ``hook_response``."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            return _FakeCompleted(0, "")
        if cmd[:2] == ["git", "rev-parse"]:
            return _FakeCompleted(0, "deadbeef\n")
        if callable(hook_response):
            return hook_response(cmd)
        return hook_response

    return _fake


# --- CLI-driven markdown/JSON rendering ---------------------------------------


def test_edge_all_timed_out_repetitions_markdown_reports_no_latency_figure(
    monkeypatch: pytest.MonkeyPatch, repo: Path, tmp_path: Path
) -> None:
    """Every repetition excluded: summaries empty, markdown says so, CLI still exits 0 (C2)."""

    def _hook_response(cmd: list[str]) -> _FakeCompleted:
        raise subprocess.TimeoutExpired(cmd, 1.0, output=b"")

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))
    md_path = tmp_path / "out.md"
    json_path = tmp_path / "out.json"

    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--repetitions",
            "2",
            "--markdown",
            str(md_path),
            "--json",
            str(json_path),
        ]
    )

    assert rc == 0
    body = md_path.read_text(encoding="utf-8")
    assert "No latency figure is reported" in body
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["run_status_counts"] == {"timeout": 2}
    assert data["summaries"] == []


def test_edge_single_repetition_markdown_carries_the_stated_limitation(
    monkeypatch: pytest.MonkeyPatch, repo: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", _git_aware(_FakeCompleted(0, _TWO_JOB_STDOUT)))
    md_path = tmp_path / "single.md"
    json_path = tmp_path / "single.json"

    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--repetitions",
            "1",
            "--markdown",
            str(md_path),
            "--json",
            str(json_path),
        ]
    )

    assert rc == 0
    body = md_path.read_text(encoding="utf-8")
    assert "the relative truncation check cannot fire" in body
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["runs"][0]["status"] == "complete"


def test_positive_include_incomplete_flag_restores_the_truncated_run_via_cli(
    monkeypatch: pytest.MonkeyPatch, repo: Path, tmp_path: Path
) -> None:
    calls = {"n": 0}

    def _hook_response(_cmd: list[str]) -> _FakeCompleted:
        calls["n"] += 1
        return _FakeCompleted(0, _TWO_JOB_STDOUT if calls["n"] == 1 else _ONE_JOB_STDOUT)

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))
    json_path = tmp_path / "out.json"

    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--repetitions",
            "2",
            "--include-incomplete",
            "--json",
            str(json_path),
        ]
    )

    assert rc == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    hook_summary = next(s for s in data["summaries"] if s["scope"] == "__hook__")
    assert hook_summary["n"] == 2


def test_negative_without_include_incomplete_the_truncated_run_is_excluded_via_cli(
    monkeypatch: pytest.MonkeyPatch, repo: Path, tmp_path: Path
) -> None:
    """The control for the test above: the flag, not something else, is what changes n."""
    calls = {"n": 0}

    def _hook_response(_cmd: list[str]) -> _FakeCompleted:
        calls["n"] += 1
        return _FakeCompleted(0, _TWO_JOB_STDOUT if calls["n"] == 1 else _ONE_JOB_STDOUT)

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))
    json_path = tmp_path / "out.json"

    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--repetitions",
            "2",
            "--json",
            str(json_path),
        ]
    )

    assert rc == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    hook_summary = next(s for s in data["summaries"] if s["scope"] == "__hook__")
    assert hook_summary["n"] == 1


# --- gate_latency_io._exclusion_sentence (unit) -------------------------------


_BASE_REPORT = GateLatencyReport(
    commit_sha="deadbeef",
    captured_at="2026-01-01T00:00:00+00:00",
    command="cmd",
    hook="pre-commit",
    change_class="none",
    files=[],
    repetitions=2,
    host=HostProfile(
        captured_at="2026-01-01T00:00:00+00:00", cpu_count=4, platform="t", python_version="3.14.0"
    ),
    runs=[],
    summaries=[],
    declared_budget_seconds=None,
    percentile_note=None,
    stdin_ref_line_supplied=False,
    hook_args=[],
    forced=False,
    exclusions=[],
)


def _report(**overrides: Any) -> GateLatencyReport:
    return dataclasses.replace(_BASE_REPORT, **overrides)


def test_edge_exclusion_sentence_states_no_repetitions_when_totally_empty() -> None:
    """No override: ``run_status_counts`` and ``runs`` stay at ``_BASE_REPORT``'s empty default."""
    report = _report()
    (sentence,) = gl_io._exclusion_sentence(report)
    assert sentence == "No repetitions were run."


def test_positive_exclusion_sentence_states_full_coverage_when_nothing_excluded() -> None:
    report = _report(run_status_counts={"complete": 2})
    (sentence,) = gl_io._exclusion_sentence(report)
    assert sentence == "The summaries below cover all 2 repetitions."


def test_negative_exclusion_sentence_names_the_count_and_reason_when_some_excluded() -> None:
    report = _report(run_status_counts={"complete": 1, "truncated": 1})
    (sentence,) = gl_io._exclusion_sentence(report)
    assert "1 of 2 repetitions were excluded" in sentence
    assert "1 truncated" in sentence


def test_negative_exclusion_sentence_states_no_latency_figure_when_none_complete() -> None:
    report = _report(run_status_counts={"timeout": 2})
    (sentence,) = gl_io._exclusion_sentence(report)
    assert "No latency figure is reported" in sentence
    assert "2 timeout" in sentence


def test_positive_exclusion_sentence_names_include_incomplete_when_set() -> None:
    report = _report(run_status_counts={"complete": 1, "truncated": 1}, include_incomplete=True)
    (sentence,) = gl_io._exclusion_sentence(report)
    assert "--include-incomplete" in sentence
