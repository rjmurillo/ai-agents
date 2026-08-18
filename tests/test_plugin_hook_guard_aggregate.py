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
import os
import subprocess
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
    """Without a status-check function the aggregate is skipped on a failure.

    A skipped required check does not report, so the pull request waits forever
    rather than showing a red guard. `!cancelled()` keeps that property: GitHub
    documents it as the recommended alternative to `always()` for running a job
    "regardless of its success or failure". `always()` itself is now rejected
    because it also ran during cancellation, publishing a red guard for a
    superseded run (#5097). Full contract in
    `tests/workflows/test_aggregator_cancellation_guard.py`.
    """
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    condition = str(document["jobs"]["guard-result"]["if"])
    assert "!cancelled()" in condition
    assert "always()" not in condition


def test_windows_is_covered_on_a_real_windows_runner() -> None:
    """Windows is the platform the customer reported, so it cannot be dropped."""
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    text = workflow_path.read_text(encoding="utf-8")
    assert "windows-latest" in text


def test_no_guard_job_is_conditional() -> None:
    """No matrix job may carry an `if:`, which would let it skip silently.

    Sol's guard-integrity review named three ways this workflow could be
    weakened without looking weakened: reintroducing a path filter, making a
    job conditional, and dropping a job from the aggregate's `needs`. The
    other two are covered by sibling tests; this covers the second.

    `guard-result` is exempt because its `if: ${{ !cancelled() }}` is what
    makes it report at all when an upstream job fails.
    """
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    conditional = {
        name: job.get("if")
        for name, job in document["jobs"].items()
        if name != "guard-result" and job.get("if") is not None
    }
    assert not conditional, f"guard jobs must not be conditional: {conditional}"


def test_container_image_is_pinned_by_digest() -> None:
    """A mutable tag lets the vanilla row's environment change under us."""
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    for name, job in document["jobs"].items():
        container = job.get("container")
        if not container:
            continue
        image = container if isinstance(container, str) else container.get("image", "")
        assert "@sha256:" in image, f"job {name} must pin its container by digest, got {image}"


def test_vanilla_rows_use_a_real_json_parser() -> None:
    """The hook command must be extracted with a parser, not grep and sed.

    The command contains escaped quotes, so a `"[^"]*"` pattern truncates at
    the first one and yields an empty string. An empty command makes the shell
    exit 0, which would satisfy the did-not-deny assertion while testing
    nothing. Measured: grep produced 0 characters where the real command is
    1234.

    Extraction now lives in Python (`json.loads`) rather than in the workflow,
    so this asserts on the script and on the absence of the old shell pattern.
    """
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert 'grep -o \'"bash": "' not in workflow_text, "never parse hooks.json with grep"

    guard = _REPO_ROOT / "scripts" / "ci" / "vanilla_hook_guard.py"
    guard_text = guard.read_text(encoding="utf-8")
    assert "json.loads" in guard_text, "extraction must use a real JSON parser"


def test_vanilla_rows_keep_logic_out_of_the_workflow() -> None:
    """ADR-006. The vanilla rows previously carried 40 line shell blocks.

    Two copies of the same assertions, one bash and one PowerShell, had already
    drifted in what they checked, and neither could be unit tested.
    """
    yaml = pytest.importorskip("yaml")
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "installed-plugin-hook-guard.yml"
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    for name in ("vanilla-linux", "vanilla-windows"):
        for step in document["jobs"][name]["steps"]:
            run = step.get("run", "")
            code_lines = [
                line for line in str(run).splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            assert len(code_lines) <= 3, (
                f"{name} step {step.get('name')!r} has {len(code_lines)} code lines; "
                "move logic into a Python script per ADR-006"
            )


def test_assert_guard_jobs_succeeded_cli_exits_nonzero(tmp_path: Path) -> None:
    """Drive the real CLI, not the imported helper.

    The exit-contract ratchet credits a nonzero assertion only when it shares a
    test function with an invocation of that script's main or a subprocess call
    naming its path. That narrowness is deliberate: a looser rule credited
    workflow-wiring assertions, which are the first test an extraction PR
    writes and which prove nothing about the CLI.
    """
    script = _REPO_ROOT / ".github" / "scripts" / "assert_guard_jobs_succeeded.py"
    env = dict(os.environ)
    env["NEEDS_JSON"] = json.dumps({"vanilla-windows": {"result": "failure"}})
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert proc.returncode != 0
    assert "vanilla-windows" in proc.stderr


def test_assert_guard_jobs_succeeded_cli_exits_zero_when_all_pass(tmp_path: Path) -> None:
    script = _REPO_ROOT / ".github" / "scripts" / "assert_guard_jobs_succeeded.py"
    env = dict(os.environ)
    env["NEEDS_JSON"] = json.dumps({"vanilla-windows": {"result": "success"}})
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert proc.returncode == 0
