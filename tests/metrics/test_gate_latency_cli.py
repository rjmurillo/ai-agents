"""CLI-level tests for gate_latency.py (REQ-027 T7).

Split from ``test_gate_latency.py`` to keep both files under the project's
500-line taste-lint ceiling; see that module's docstring for the rationale
and the full three-way split. Covers ``main``'s argument validation and
exit-code contract (AC-07), the never-gates matrix that makes DR1
verifiable (AC-06), AC-13's never-wired-into-a-gate guarantee, and the
``__main__`` subprocess entry point. ``subprocess.run`` is monkeypatched
throughout except the one test that deliberately drives the real CLI
entry point in a subprocess to prove the ``if __name__ == "__main__"``
wiring; neither invokes a real lefthook hook.
"""

from __future__ import annotations

import json
import subprocess
import sys
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


# --- Never-gates matrix (AC-06, AC-07, DR1) ----------------------------------


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


# --- CLI exit-code matrix ----------------------------------------------------


def test_negative_dirty_tree_without_allow_dirty_exits_1(repo: Path) -> None:
    _write(repo, "dirty.txt", "uncommitted\n")
    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "1"]) == 1


def test_positive_dirty_tree_with_allow_dirty_proceeds(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    _write(repo, "dirty.txt", "uncommitted\n")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: (
            _FakeCompleted(0, " M dirty.txt\n")
            if cmd[:2] == ["git", "status"]
            else _FakeCompleted(0, REAL_CAPTURED_STDOUT)
        ),
    )
    rc = gl.main(
        ["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "1", "--allow-dirty"]
    )
    assert rc == 0


def test_negative_missing_repo_exits_2(tmp_path: Path) -> None:
    assert gl.main(["--repo", str(tmp_path / "nope"), "--hook", "pre-commit"]) == 2


def test_negative_non_git_dir_exits_2(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert gl.main(["--repo", str(plain), "--hook", "pre-commit"]) == 2


def test_negative_missing_lefthook_yml_exits_2(tmp_path: Path) -> None:
    root = tmp_path / "no-lefthook"
    root.mkdir()
    git(root, "init", "-q")
    assert gl.main(["--repo", str(root), "--hook", "pre-commit"]) == 2


def test_negative_invalid_lefthook_yml_exits_2(tmp_path: Path) -> None:
    root = tmp_path / "bad-lefthook"
    root.mkdir()
    git(root, "init", "-q")
    _write(root, "lefthook.yml", "- just\n- a\n- list\n")
    assert gl.main(["--repo", str(root), "--hook", "pre-commit"]) == 2


def test_negative_unknown_hook_exits_2(repo: Path) -> None:
    assert gl.main(["--repo", str(repo), "--hook", "does-not-exist"]) == 2


def test_negative_non_hook_top_level_key_is_not_accepted_as_a_hook(repo: Path) -> None:
    """``min_version`` etc. are top-level config keys, not hooks (verified against lefthook.yml)."""
    assert gl.main(["--repo", str(repo), "--hook", "min_version"]) == 2


def test_negative_unknown_change_class_exits_2(repo: Path) -> None:
    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--change-class", "nope"]) == 2


def test_negative_missing_change_class_path_exits_2(repo: Path) -> None:
    (repo / "README.md").unlink()
    rc = gl.main(["--repo", str(repo), "--hook", "pre-commit", "--change-class", "markdown"])
    assert rc == 2


def test_negative_repetitions_below_one_exits_2(repo: Path) -> None:
    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "0"]) == 2
    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--repetitions", "-1"]) == 2


def test_negative_missing_lefthook_binary_exits_2(repo: Path) -> None:
    rc = gl.main(
        [
            "--repo",
            str(repo),
            "--hook",
            "pre-commit",
            "--lefthook-bin",
            "/definitely/does/not/exist/lefthook",
        ]
    )
    assert rc == 2


def test_positive_change_class_file_lists_all_exist_in_this_repository() -> None:
    """AC-08's startup validation over the real, shipped table."""
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    for name, paths in gl.CHANGE_CLASSES.items():
        for rel in paths:
            missing_msg = f"change class {name!r} names a missing path {rel!r}"
            assert (REPO_ROOT / rel).is_file(), missing_msg


# --- AC-13: never wired into a gate ------------------------------------------


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


# --- Command normalization ---------------------------------------------------


def test_positive_normalized_command_args_replaces_repo_value() -> None:
    args = ["--repo", "/home/alice/checkout", "--hook", "pre-commit", "--json", "out.json"]
    normalized = gl._normalized_command_args(args)
    assert normalized == ["--repo", "<repo>", "--hook", "pre-commit", "--json", "out.json"]


def test_edge_normalized_command_args_handles_repo_equals_form() -> None:
    args = ["--repo=/home/alice/checkout", "--hook", "pre-commit"]
    normalized = gl._normalized_command_args(args)
    assert normalized == ["--repo=<repo>", "--hook", "pre-commit"]


# --- CLI entry point via subprocess (proves the __main__ wiring) ------------


def test_cli_entry_point_via_subprocess_unknown_hook_exits_2(repo: Path) -> None:
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "metrics" / "gate_latency.py"),
            "--repo",
            str(repo),
            "--hook",
            "does-not-exist",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
