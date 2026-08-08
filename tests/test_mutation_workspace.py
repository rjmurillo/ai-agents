"""Regression tests for crash-safe mutation worktree isolation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.testing import mutation_workspace, mutation_workspace_git
from scripts.testing.mutation_harness import MutationEntry, MutationRunner
from scripts.testing.mutation_workspace import (
    EXIT_BLOCKED,
    EXIT_OK,
    SCRATCH_DIRECTORY,
    MutationInterrupted,
    MutationWorkspaceError,
    check_markers,
    isolated_mutation_worktree,
    marker_directory,
    recover_marker,
    recover_markers,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("scripts/validation/portability_common.py")


def _create_repository(path: Path) -> tuple[Path, Path]:
    path.mkdir()
    target = path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    commands = (
        ("init", "--quiet"),
        ("add", "target.py"),
        (
            "-c",
            "user.name=Mutation Test",
            "-c",
            "user.email=mutation@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "test: initialize repository",
        ),
    )
    for command in commands:
        subprocess.run(["git", *command], cwd=path, check=True)
    return path, target


def _child_process() -> subprocess.Popen[str]:
    code = """
import json
import sys
import time
from pathlib import Path
from scripts.testing.mutation_workspace import isolated_mutation_worktree

repo_root = Path(sys.argv[1])
target = Path(sys.argv[2])
with isolated_mutation_worktree(repo_root, [target]) as workspace:
    scratch_target = workspace.root / target
    scratch_target.write_text("# forced mutation\\n", encoding="utf-8")
    print(json.dumps({
        "marker": str(workspace.marker_path),
        "scratch": str(workspace.root),
    }), flush=True)
    time.sleep(300)
"""
    return subprocess.Popen(
        [sys.executable, "-c", code, str(REPO_ROOT), str(TARGET)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _cleanup_signal_child_process() -> subprocess.Popen[str]:
    code = """
import os
import signal
import sys
from pathlib import Path
from scripts.testing import mutation_workspace

repo_root = Path(sys.argv[1])
target = Path(sys.argv[2])
remove_worktree = mutation_workspace._remove_worktree

def signal_during_cleanup(root, scratch):
    os.kill(os.getpid(), signal.SIGTERM)
    remove_worktree(root, scratch)

mutation_workspace._remove_worktree = signal_during_cleanup
with mutation_workspace.isolated_mutation_worktree(repo_root, [target]) as workspace:
    print(f"{workspace.marker_path}|{workspace.root}", flush=True)
"""
    return subprocess.Popen(
        [sys.executable, "-c", code, str(REPO_ROOT), str(TARGET)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _ready_workspace(process: subprocess.Popen[str]) -> dict[str, str]:
    assert process.stdout is not None
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"mutation child exited before ready: {stderr}")
    payload = json.loads(line)
    assert isinstance(payload, dict)
    return payload


def _stop_process(process: subprocess.Popen[str], signum: signal.Signals) -> int:
    os.kill(process.pid, signum)
    return process.wait(timeout=30)


def test_normal_completion_removes_marker_and_scratch() -> None:
    active_before = (REPO_ROOT / TARGET).read_bytes()

    with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
        scratch = workspace.root
        marker = workspace.marker_path
        (scratch / TARGET).write_text("# normal mutation\n", encoding="utf-8")
        assert marker.is_file()

    assert not marker.exists()
    assert not scratch.exists()
    assert (REPO_ROOT / TARGET).read_bytes() == active_before


def test_shared_mutation_runner_never_writes_tracked_source() -> None:
    active_target = REPO_ROOT / TARGET
    original = active_target.read_text(encoding="utf-8")
    old = "not isinstance(value, int) or isinstance(value, bool)"
    entry = MutationEntry(
        name="tracked-source-isolation",
        path=active_target,
        old=old,
        new="not isinstance(value, int)",
        command=(sys.executable, "-c", "raise SystemExit(1)"),
    )

    result = MutationRunner(cwd=REPO_ROOT).run_entry(entry)

    assert result.caught
    assert active_target.read_text(encoding="utf-8") == original


def test_untracked_target_is_rejected(tmp_path: Path) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    untracked = repo / "untracked.py"
    untracked.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(MutationWorkspaceError, match="not tracked by git"):
        with isolated_mutation_worktree(repo, [untracked]):
            pytest.fail("untracked target entered mutation workspace")


def test_dirty_target_is_rejected(tmp_path: Path) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    target.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(MutationWorkspaceError, match="uncommitted changes"):
        with isolated_mutation_worktree(repo, [target]):
            pytest.fail("dirty target entered mutation workspace")


def test_staged_target_is_rejected(tmp_path: Path) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    target.write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "target.py"], cwd=repo, check=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(MutationWorkspaceError, match="uncommitted changes"):
        with isolated_mutation_worktree(repo, [target]):
            pytest.fail("staged target entered mutation workspace")


def test_untracked_hard_link_to_tracked_target_is_rejected(tmp_path: Path) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    alias = repo / "alias.py"
    os.link(target, alias)
    entry = MutationEntry(
        name="hard-link-alias",
        path=alias,
        old="VALUE = 1",
        new="VALUE = 2",
        command=(sys.executable, "-c", "raise SystemExit(1)"),
    )

    with pytest.raises(MutationWorkspaceError, match="aliases tracked path"):
        MutationRunner(cwd=repo).run_entry(entry)

    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_git_failure_does_not_fall_back_to_active_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = subprocess.CompletedProcess(
        args=["git", "rev-parse"],
        returncode=2,
        stdout="",
        stderr="injected git failure",
    )
    monkeypatch.setattr(mutation_workspace_git, "run_git", lambda *_args: failure)

    with pytest.raises(MutationWorkspaceError, match="injected git failure"):
        mutation_workspace.tracked_repository_path(REPO_ROOT / TARGET)


def test_git_pointer_environment_cannot_redirect_tracking_or_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_marker_directory = marker_directory(REPO_ROOT)
    common_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    common_dir = Path(common_dir_result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = REPO_ROOT / common_dir
    hostile_environment = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.worktree",
        "GIT_CONFIG_VALUE_0": "/",
        "GIT_DIR": str(common_dir.resolve()),
        "GIT_INDEX_FILE": str(REPO_ROOT / "invalid-index"),
        "GIT_WORK_TREE": "/",
    }
    for key, value in hostile_environment.items():
        monkeypatch.setenv(key, value)

    assert mutation_workspace.tracked_repository_path(REPO_ROOT / TARGET) == (
        REPO_ROOT,
        TARGET,
    )
    assert marker_directory(REPO_ROOT) == baseline_marker_directory


def test_interruption_during_worktree_add_cleans_partial_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    observed: dict[str, Path] = {}

    def interrupt_add(_repo_root: Path, scratch_root: Path) -> None:
        observed["scratch"] = scratch_root
        scratch_root.mkdir(parents=True)
        raise MutationInterrupted(128 + signal.SIGTERM)

    monkeypatch.setattr(mutation_workspace, "_add_worktree", interrupt_add)

    with pytest.raises(MutationInterrupted):
        with isolated_mutation_worktree(repo, [target]):
            pytest.fail("interrupted setup yielded a workspace")

    assert not observed["scratch"].exists()
    assert not list(marker_directory(repo).iterdir())


def test_signal_after_worktree_add_still_runs_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    observed: dict[str, Path] = {}
    add_worktree = mutation_workspace._add_worktree

    def add_then_signal(repo_root: Path, scratch_root: Path) -> None:
        add_worktree(repo_root, scratch_root)
        observed["scratch"] = scratch_root
        os.kill(os.getpid(), signal.SIGTERM)

    monkeypatch.setattr(mutation_workspace, "_add_worktree", add_then_signal)

    with pytest.raises(MutationInterrupted):
        with isolated_mutation_worktree(repo, [target]):
            pytest.fail("signal after add yielded a workspace")

    assert not observed["scratch"].exists()
    assert not list(marker_directory(repo).iterdir())


def test_finished_marker_rewrite_does_not_follow_hard_link(tmp_path: Path) -> None:
    marker = tmp_path / "marker.json"
    external = tmp_path / "external.json"
    external.write_text('{"protected": true}\n', encoding="utf-8")
    os.link(external, marker)
    payload = {"schema_version": 1, "pid": os.getpid()}

    mutation_workspace._mark_run_finished(marker, payload)

    assert json.loads(marker.read_text(encoding="utf-8"))["pid"] is None
    assert external.read_text(encoding="utf-8") == '{"protected": true}\n'


def test_remove_worktree_clears_fresh_registration_when_directory_missing(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    scratch = repo / SCRATCH_DIRECTORY / "missing-worktree"
    mutation_workspace_git.add_worktree(repo, scratch)
    shutil.rmtree(scratch)

    mutation_workspace_git.remove_worktree(repo, scratch)

    assert scratch not in mutation_workspace_git.registered_worktrees(repo)


def test_cleanup_removes_scratch_and_preserves_body_error_after_active_drift(
    tmp_path: Path,
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    original = target.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="body failure"):
        with isolated_mutation_worktree(repo, [target]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path
            target.write_text("VALUE = 2\n", encoding="utf-8")
            raise RuntimeError("body failure")

    assert not scratch.exists()
    assert marker.exists()
    assert json.loads(marker.read_text(encoding="utf-8"))["pid"] is None

    target.write_text(original, encoding="utf-8")
    assert recover_marker(repo, marker) == EXIT_OK


def test_exception_removes_marker_and_scratch() -> None:
    with pytest.raises(RuntimeError, match="forced crash"):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path
            raise RuntimeError("forced crash")

    assert not marker.exists()
    assert not scratch.exists()


def test_timeout_removes_marker_and_scratch() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        with isolated_mutation_worktree(REPO_ROOT, [TARGET]) as workspace:
            scratch = workspace.root
            marker = workspace.marker_path
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                check=False,
                timeout=0.01,
            )

    assert not marker.exists()
    assert not scratch.exists()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_catchable_signal_removes_marker_and_scratch(
    signum: signal.Signals,
) -> None:
    process = _child_process()
    workspace = _ready_workspace(process)

    returncode = _stop_process(process, signum)

    assert returncode == 128 + signum
    assert not Path(workspace["marker"]).exists()
    assert not Path(workspace["scratch"]).exists()


def test_signal_during_cleanup_is_deferred_until_cleanup_completes() -> None:
    process = _cleanup_signal_child_process()
    assert process.stdout is not None
    ready = process.stdout.readline().strip()
    assert ready
    marker, scratch = (Path(value) for value in ready.split("|", maxsplit=1))

    assert process.wait(timeout=30) == 128 + signal.SIGTERM
    assert not marker.exists()
    assert not scratch.exists()


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL unavailable")
def test_sigkill_leaves_marker_blocks_push_and_recovers(capsys: pytest.CaptureFixture[str]) -> None:
    active_before = (REPO_ROOT / TARGET).read_bytes()
    process = _child_process()
    workspace = _ready_workspace(process)

    returncode = _stop_process(process, signal.SIGKILL)

    try:
        assert returncode == -signal.SIGKILL
        assert Path(workspace["marker"]).is_file()
        assert Path(workspace["scratch"]).is_dir()
        assert (REPO_ROOT / TARGET).read_bytes() == active_before

        assert check_markers(REPO_ROOT) == EXIT_BLOCKED
        error = capsys.readouterr().err
        assert "push blocked" in error
        assert TARGET.as_posix() in error
        assert "[UNCHANGED]" in error
    finally:
        assert recover_marker(REPO_ROOT, Path(workspace["marker"])) == EXIT_OK

    assert not Path(workspace["marker"]).exists()
    assert not Path(workspace["scratch"]).exists()


def test_concurrent_runs_use_distinct_markers_and_worktrees() -> None:
    first = _child_process()
    second = _child_process()
    workspaces: list[dict[str, str]] = []
    try:
        first_workspace = _ready_workspace(first)
        second_workspace = _ready_workspace(second)
        workspaces.extend((first_workspace, second_workspace))

        assert first_workspace["marker"] != second_workspace["marker"]
        assert first_workspace["scratch"] != second_workspace["scratch"]

        assert _stop_process(first, signal.SIGTERM) == 128 + signal.SIGTERM
        assert _stop_process(second, signal.SIGTERM) == 128 + signal.SIGTERM
        assert not Path(first_workspace["marker"]).exists()
        assert not Path(second_workspace["marker"]).exists()
    finally:
        for process in (first, second):
            if process.poll() is None:
                _stop_process(process, signal.SIGKILL)
        for workspace in workspaces:
            marker = Path(workspace["marker"])
            if marker.exists():
                assert recover_marker(REPO_ROOT, marker) == EXIT_OK


def test_recovery_refuses_changed_active_target(capsys: pytest.CaptureFixture[str]) -> None:
    marker_root = marker_directory(REPO_ROOT)
    marker_root.mkdir(parents=True, exist_ok=True)
    marker = marker_root / "test-modified-source.json"
    scratch = (REPO_ROOT / SCRATCH_DIRECTORY / "test-modified-source").resolve()
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": 999_999_999,
                "repo_root": str(REPO_ROOT),
                "scratch_worktree": str(scratch),
                "targets": [
                    {
                        "path": TARGET.as_posix(),
                        "sha256": hashlib.sha256(b"different").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        assert recover_markers(REPO_ROOT) == EXIT_BLOCKED
        error = capsys.readouterr().err
        assert TARGET.as_posix() in error
        assert "MODIFIED" in error
        assert marker.exists()
    finally:
        marker.unlink(missing_ok=True)


def test_non_file_marker_blocks_push(capsys: pytest.CaptureFixture[str]) -> None:
    invalid_marker = marker_directory(REPO_ROOT) / "invalid-marker"
    invalid_marker.mkdir(parents=True)
    try:
        assert check_markers(REPO_ROOT) == EXIT_BLOCKED
        error = capsys.readouterr().err
        assert "push blocked" in error
        assert "INVALID" in error
    finally:
        invalid_marker.rmdir()


def test_pre_push_runs_mutation_safety_before_validation() -> None:
    config = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = config["pre-push"]["jobs"]
    names = [job.get("name") for job in jobs]

    assert names.index("mutation-safety") < names.index("push-ref-staleness")
    job = next(item for item in jobs if item.get("name") == "mutation-safety")
    assert job["run"].endswith("scripts.testing.mutation_workspace check")
