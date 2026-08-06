#!/usr/bin/env python3
"""Tests for the plugin hook guard aggregate status (issue #4672).

The aggregate exists so branch protection can require one context instead of
every matrix leg by name. Its only job is to answer whether the guard actually
ran and passed, so the interesting cases are the ones where it must REFUSE to
report success: a job that failed, a job that was skipped or cancelled, and an
upstream payload that is empty or malformed.

A required check that reports success when nothing ran is the false-green this
guard was created to prevent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "assert_guard_jobs_succeeded.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("assert_guard_jobs_succeeded", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["assert_guard_jobs_succeeded"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="guard")
def guard_fixture():
    return _load_module()


def test_script_exists() -> None:
    assert _SCRIPT.is_file(), f"aggregate logic script missing at {_SCRIPT}"


def test_all_success_exits_zero(guard, monkeypatch: pytest.MonkeyPatch) -> None:
    needs = {"hook-positive": {"result": "success"}, "vanilla-windows": {"result": "success"}}
    monkeypatch.setenv("NEEDS_JSON", json.dumps(needs))
    assert guard.main([]) == 0


@pytest.mark.parametrize("bad_result", ["failure", "skipped", "cancelled", "missing", ""])
def test_non_success_result_exits_nonzero(
    guard, monkeypatch: pytest.MonkeyPatch, bad_result: str
) -> None:
    """Only 'success' may pass.

    'skipped' matters most: a path filter, a cancelled sibling, or a dependency
    that never ran would otherwise let the required check report green while
    verifying nothing.
    """
    needs = {"hook-positive": {"result": "success"}, "vanilla-windows": {"result": bad_result}}
    monkeypatch.setenv("NEEDS_JSON", json.dumps(needs))
    assert guard.main([]) != 0


def test_failing_job_is_named_in_output(
    guard, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    needs = {"vanilla-windows": {"result": "skipped"}}
    monkeypatch.setenv("NEEDS_JSON", json.dumps(needs))
    guard.main([])
    captured = capsys.readouterr()
    assert "vanilla-windows" in captured.err
    assert "skipped" in captured.err


def test_empty_needs_exits_nonzero(guard, monkeypatch: pytest.MonkeyPatch) -> None:
    """No upstream jobs at all means the guard did not run."""
    monkeypatch.setenv("NEEDS_JSON", json.dumps({}))
    assert guard.main([]) != 0


def test_absent_needs_env_exits_nonzero(guard, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEEDS_JSON", raising=False)
    assert guard.main([]) != 0


def test_malformed_json_exits_nonzero(guard, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEEDS_JSON", "{not json")
    assert guard.main([]) != 0


def test_non_object_json_exits_nonzero(guard, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEEDS_JSON", json.dumps(["success"]))
    assert guard.main([]) != 0


def test_guard_workflow_is_not_path_filtered() -> None:
    """The guard must run on every pull request.

    A path filter would leave it silent for changes that break the hooks
    indirectly, and a path-filtered required check never reports on unrelated
    pull requests, which stalls merges instead of guarding anything.
    """
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    # PyYAML parses the bare key `on` as boolean True.
    triggers = document.get("on") or document.get(True)
    assert "pull_request" in triggers
    pull_request = triggers["pull_request"] or {}
    assert "paths" not in pull_request, "guard must not be path filtered"
    assert "paths-ignore" not in pull_request, "guard must not be path filtered"


def test_guard_result_depends_on_every_other_job() -> None:
    """The aggregate must cover every job, or a leg can fail unnoticed."""
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    assert "guard-result" in jobs
    declared = set(jobs["guard-result"]["needs"])
    others = {name for name in jobs if name != "guard-result"}
    assert declared == others, f"guard-result must depend on every job; missing {others - declared}"


def test_guard_result_runs_even_when_dependencies_fail() -> None:
    """Without `if: always()` the aggregate is skipped when a dependency fails.

    A skipped required check does not report, so the pull request waits forever
    rather than showing a red guard.
    """
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    condition = document["jobs"]["guard-result"]["if"]
    assert "always()" in str(condition)


def test_windows_is_covered_on_a_real_windows_runner() -> None:
    """Windows is the platform the customer reported, so it cannot be dropped."""
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    text = workflow_path.read_text(encoding="utf-8")
    assert "windows-latest" in text
    jobs = document["jobs"]
    windows_jobs = [
        name
        for name, job in jobs.items()
        if "windows-latest" in str(job.get("runs-on", "")) + str(job.get("strategy", ""))
    ]
    assert windows_jobs, "at least one job must run on a real Windows runner"
