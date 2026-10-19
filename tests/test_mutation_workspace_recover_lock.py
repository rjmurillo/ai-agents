"""Regression tests for recovering a scratch worktree that git left locked."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts.testing import mutation_workspace, mutation_workspace_git, mutation_workspace_recovery
from scripts.testing.mutation_workspace import (
    EXIT_BLOCKED,
    EXIT_OK,
    MutationWorkspaceError,
    marker_directory,
    scratch_directory,
)


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


def _write_marker_for(
    repo: Path, target: Path, scratch: Path, name: str, *, age_seconds: float = 3600
) -> Path:
    marker_root = marker_directory(repo)
    marker_root.mkdir(parents=True, exist_ok=True)
    marker = marker_root / f"{name}.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pid": 999_999_999,
                "repo_root": str(repo),
                "scratch_worktree": str(scratch),
                "targets": [
                    {
                        "path": target.name,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    aged = time.time() - age_seconds
    os.utime(marker, (aged, aged))
    return marker


def _add_locked_worktree(repo: Path, name: str, reason: str) -> Path:
    scratch = scratch_directory(repo) / name
    mutation_workspace_git.add_worktree(repo, scratch)
    subprocess.run(
        ["git", "worktree", "lock", "--reason", reason, str(scratch)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return scratch


def test_recover_clears_a_worktree_locked_as_initializing(tmp_path: Path) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch = _add_locked_worktree(repo, "stale-init", "initializing")
    marker = _write_marker_for(repo, target, scratch, "stale-init")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_OK

    assert not marker.exists()
    assert not scratch.exists()
    assert mutation_workspace.check_markers(repo) == EXIT_OK


def test_recover_keeps_a_worktree_with_a_different_lock_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch = _add_locked_worktree(repo, "held", "held by another tool")
    marker = _write_marker_for(repo, target, scratch, "held")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    error = capsys.readouterr().err
    assert "git worktree unlock" in error
    assert marker.exists()
    assert scratch.exists()
    subprocess.run(["git", "worktree", "unlock", str(scratch)], cwd=repo, check=True)


def test_recover_refuses_a_modified_target_even_when_locked_as_initializing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch = _add_locked_worktree(repo, "leaked", "initializing")
    marker = _write_marker_for(repo, target, scratch, "leaked")
    target.write_text("VALUE = 2\n", encoding="utf-8")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    assert "MODIFIED" in capsys.readouterr().err
    assert marker.exists()
    assert scratch.exists()
    subprocess.run(["git", "worktree", "unlock", str(scratch)], cwd=repo, check=True)


def test_unlock_stale_worktree_never_touches_a_worktree_outside_scratch(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    outside = tmp_path / "outside-worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(outside), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "lock", "--reason", "initializing", str(outside)],
        cwd=repo,
        check=True,
    )

    with pytest.raises(MutationWorkspaceError, match="outside"):
        mutation_workspace_git.unlock_stale_worktree(repo, outside, 0.0)

    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "locked initializing" in listing


def test_unlock_stale_worktree_reports_false_for_an_unlocked_worktree(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    scratch = scratch_directory(repo) / "plain"
    mutation_workspace_git.add_worktree(repo, scratch)

    assert mutation_workspace_git.unlock_stale_worktree(repo, scratch, 0.0) is False

    mutation_workspace_git.remove_worktree(repo, scratch)


def test_recover_waits_while_the_initializing_marker_is_young(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch = _add_locked_worktree(repo, "young", "initializing")
    marker = _write_marker_for(repo, target, scratch, "young", age_seconds=1)

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    assert "still initializing" in capsys.readouterr().err
    assert marker.exists()
    assert scratch.exists()
    subprocess.run(["git", "worktree", "unlock", str(scratch)], cwd=repo, check=True)


def test_recover_keeps_a_lock_reason_that_only_contains_initializing(
    tmp_path: Path,
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch = _add_locked_worktree(repo, "padded", " initializing ")
    marker = _write_marker_for(repo, target, scratch, "padded")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    assert marker.exists()
    assert scratch.exists()
    subprocess.run(["git", "worktree", "unlock", str(scratch)], cwd=repo, check=True)


def _add_half_created_worktree(repo: Path, name: str) -> tuple[Path, Path]:
    """Add a worktree, then strip the admin files git writes last (issue #6717)."""
    scratch = scratch_directory(repo) / name
    mutation_workspace_git.add_worktree(repo, scratch)
    pointer = (scratch / ".git").read_text(encoding="utf-8").strip()
    admin = Path(pointer.removeprefix("gitdir:").strip())
    for leftover in ("commondir", "index", "ORIG_HEAD"):
        (admin / leftover).unlink(missing_ok=True)
    return scratch, admin


def _registered(repo: Path) -> str:
    return subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_recover_clears_a_half_created_worktree_and_names_what_it_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch, admin = _add_half_created_worktree(repo, "half")
    marker = _write_marker_for(repo, target, scratch, "half")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_OK

    error = capsys.readouterr().err
    assert str(scratch) in error
    assert str(admin) in error
    assert not marker.exists()
    assert not scratch.exists()
    assert not admin.exists()
    assert str(scratch) not in _registered(repo)
    assert mutation_workspace.check_markers(repo) == EXIT_OK


def test_recover_clears_a_half_created_worktree_whose_directory_is_gone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch, admin = _add_half_created_worktree(repo, "gone")
    marker = _write_marker_for(repo, target, scratch, "gone")
    for child in sorted(scratch.rglob("*"), reverse=True):
        child.unlink() if not child.is_dir() or child.is_symlink() else child.rmdir()
    scratch.rmdir()

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_OK

    error = capsys.readouterr().err
    assert str(admin) in error
    assert not marker.exists()
    assert not admin.exists()


def test_recover_refuses_a_modified_target_for_a_half_created_worktree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch, admin = _add_half_created_worktree(repo, "modified")
    marker = _write_marker_for(repo, target, scratch, "modified")
    target.write_text("VALUE = 2\n", encoding="utf-8")

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    assert "MODIFIED" in capsys.readouterr().err
    assert marker.exists()
    assert scratch.exists()
    assert admin.exists()


def test_recover_waits_while_a_half_created_worktree_marker_is_young(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, target = _create_repository(tmp_path / "repo")
    scratch, admin = _add_half_created_worktree(repo, "young-half")
    marker = _write_marker_for(repo, target, scratch, "young-half", age_seconds=1)

    assert mutation_workspace.main(["recover", "--repo-root", str(repo)]) == EXIT_BLOCKED

    assert "half created" in capsys.readouterr().err
    assert marker.exists()
    assert scratch.exists()
    assert admin.exists()


def test_discard_half_created_worktree_leaves_a_healthy_worktree_alone(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    scratch = scratch_directory(repo) / "healthy"
    mutation_workspace_git.add_worktree(repo, scratch)

    assert mutation_workspace_recovery.discard_half_created_worktree(repo, scratch, 0.0) == ()

    assert scratch.exists()
    assert str(scratch) in _registered(repo)
    mutation_workspace_git.remove_worktree(repo, scratch)


def test_discard_half_created_worktree_leaves_a_locked_entry_alone(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    scratch, admin = _add_half_created_worktree(repo, "locked-half")
    subprocess.run(
        ["git", "worktree", "lock", "--reason", "held by another tool", str(scratch)],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    assert mutation_workspace_recovery.discard_half_created_worktree(repo, scratch, 0.0) == ()

    assert scratch.exists()
    assert admin.exists()


def test_discard_half_created_worktree_never_touches_a_path_outside_scratch(
    tmp_path: Path,
) -> None:
    repo, _target = _create_repository(tmp_path / "repo")
    outside = tmp_path / "outside-worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(outside), "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    pointer = (outside / ".git").read_text(encoding="utf-8").strip()
    admin = Path(pointer.removeprefix("gitdir:").strip())
    (admin / "commondir").unlink()

    with pytest.raises(MutationWorkspaceError, match="outside"):
        mutation_workspace_recovery.discard_half_created_worktree(repo, outside, 0.0)

    assert outside.exists()
    assert admin.exists()
