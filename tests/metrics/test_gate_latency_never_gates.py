"""Proof that the sampler cannot gate anything (REQ-027 AC-06, AC-07, AC-13, DR1).

Two halves of one claim. The matrix drives main() over hook exit codes and
durations and asserts the process still exits 0, so no metric value can decide
whether code ships. The reference tests assert the script is named by no
lefthook job, no pre_pr script and no workflow, so a later wiring fails here
rather than silently turning a measurement tool into a gate.

Split from test_gate_latency_cli.py, which held four concerns and scored 1.0
cohesion against a test-context floor of 6.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.metrics import gate_latency as gl
from tests.gc_real_git import git

_DIVIDER = "\x1b[38;2;56;56;56m" + "─" * 40 + "\x1b[0m"

# Real captured output, this session (see test_gate_latency.py's fixture of
# the same name for the full provenance note).
REAL_CAPTURED_STDOUT = (
    f"{_DIVIDER}\n"
    "summary: (done in 0.20 seconds)\n"
    "✓ security-suppressions-staged (0.20 seconds)\n"
)

_LEFTHOOK_YML = """\
pre-commit:
  piped: true
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
pre-push:
  piped: true
  jobs:
    - name: job-c
      group:
        parallel: true
        jobs:
          - name: job-c1
            run: echo c1
            timeout: 20s
          - name: job-c2
            run: echo c2
            timeout: 30s
"""


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small git repo with a real lefthook.yml and every change-class path."""
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", _LEFTHOOK_YML)
    for rel in gl.CHANGE_CLASSES.values():
        for path in rel:
            _write(root, path, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- Never-gates matrix and the reference-absence checks ---------------------

@pytest.mark.parametrize("hook_exit_code", [0, 1, 2, 130])
@pytest.mark.parametrize("duration", [0.0, 0.19, 999.5])
def test_never_gates_exit_0_regardless_of_hook_exit_code_or_duration(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    tmp_path: Path,
    hook_exit_code: int,
    duration: float,
) -> None:
    stdout = f"summary: (done in {duration} seconds)\n✔️ a-job ({duration} seconds)\n"

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            return _FakeCompleted(0, "")
        if cmd[:2] == ["git", "rev-parse"]:
            return _FakeCompleted(0, "deadbeef\n")
        return _FakeCompleted(hook_exit_code, stdout)

    monkeypatch.setattr(subprocess, "run", _fake)
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
    assert all(run["exit_code"] == hook_exit_code for run in data["runs"])


def test_negative_gate_latency_is_not_referenced_by_lefthook_yml() -> None:
    from scripts.ci.lefthook_budget_model import LEFTHOOK

    text = LEFTHOOK.read_text(encoding="utf-8")
    assert "gate_latency" not in text


def test_negative_gate_latency_is_not_referenced_by_pre_pr_scripts() -> None:
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    validation_dir = REPO_ROOT / "scripts" / "validation"
    for path in validation_dir.glob("pre_pr*.py"):
        assert "gate_latency" not in path.read_text(encoding="utf-8"), path


def test_negative_gate_latency_is_not_referenced_by_any_workflow() -> None:
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    workflows_dir = REPO_ROOT / ".github" / "workflows"
    for path in workflows_dir.glob("*.yml"):
        assert "gate_latency" not in path.read_text(encoding="utf-8"), path

