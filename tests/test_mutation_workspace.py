"""Regression tests for crash-safe mutation worktree isolation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
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
