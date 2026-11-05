"""Tests for the merge-base growth check in check_unused_arguments.py.

The baseline may only shrink. The gate reads it at ``git merge-base HEAD
<base-ref>`` and fails on any line the branch added, so a same-count swap fails
and a pure rename needs only a path change on its lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from check_unused_arguments import BASELINE_RELPATH

from tests.validation.unused_arguments_helpers import (
    UNUSED,
    UNUSED_KEY,
    add_file,
    commit,
    commit_baseline,
    git,
    make_repo,
    run_gate,
)

OTHER = "def g(args):\n    return 1\n"
OTHER_KEY = "scripts/other.py: ARG001 args"


def _base(tmp_path: Path, *lines: str) -> Path:
    """Commit a repo with ``scripts/mod.py`` and ``lines`` as the baseline, on branch ``base``."""
    repo = make_repo(tmp_path)
    commit_baseline(repo, *lines)
    commit(repo, "base")
    git(repo, "branch", "base")
    return repo


def _gate(repo: Path, *extra: str) -> int:
    return run_gate(repo, repo / BASELINE_RELPATH, "--base-ref", "base", *extra)


def test_unchanged_baseline_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _base(tmp_path, UNUSED_KEY)

    assert _gate(repo) == 0
    assert "baseline growth vs merge base" in capsys.readouterr().out


def test_removing_a_baseline_line_with_its_fix_passes(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/mod.py", "def f(path):\n    return path\n")
    commit_baseline(repo)

    assert _gate(repo) == 0


def test_a_new_finding_with_a_new_baseline_line_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/other.py", OTHER)
    commit_baseline(repo, UNUSED_KEY, OTHER_KEY)

    assert _gate(repo) == 1
    assert f"baseline line not in the merge base: {OTHER_KEY}" in capsys.readouterr().err


def test_a_same_count_swap_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Fix the listed finding, add a new one, and swap the baseline lines. The
    # line count and the findings-equal-baseline check both still hold.
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/mod.py", "def f(path):\n    return path\n")
    add_file(repo, "scripts/other.py", OTHER)
    commit_baseline(repo, OTHER_KEY)

    assert _gate(repo) == 1
    assert f"baseline line not in the merge base: {OTHER_KEY}" in capsys.readouterr().err


def test_a_duplicate_baseline_line_counts_as_growth(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/mod.py", UNUSED + "\n\ndef h(path):\n    return 2\n")
    commit_baseline(repo, UNUSED_KEY, UNUSED_KEY)

    assert _gate(repo) == 1


def test_the_branch_cannot_edit_the_ceiling_it_is_held_to(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/other.py", OTHER)
    commit_baseline(repo, UNUSED_KEY, OTHER_KEY)
    commit(repo, "feature")

    assert _gate(repo) == 1


def test_a_renamed_file_passes_when_only_the_baseline_path_changes(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    git(repo, "mv", "scripts/mod.py", "scripts/moved.py")
    commit_baseline(repo, "scripts/moved.py: ARG001 path")

    assert _gate(repo) == 0


def test_a_renamed_file_with_the_old_baseline_path_gets_a_rename_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    git(repo, "mv", "scripts/mod.py", "scripts/moved.py")

    assert _gate(repo) == 1
    err = capsys.readouterr().err
    assert "new unused argument: scripts/moved.py: ARG001 path" in err
    assert f"stale baseline entry: {UNUSED_KEY}" in err
    assert "change the path on the stale line" in err


def test_a_path_rewrite_without_a_git_rename_is_growth(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/other.py", "def f(path):\n    return 1\n")
    add_file(repo, "scripts/mod.py", "def f(path):\n    return path\n")
    commit_baseline(repo, "scripts/other.py: ARG001 path")

    assert _gate(repo) == 1


def test_a_merge_base_with_no_baseline_is_the_bootstrap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    commit(repo, "base")
    git(repo, "branch", "base")
    commit_baseline(repo, UNUSED_KEY)

    assert _gate(repo) == 0
    assert "base has no baseline yet" in capsys.readouterr().out


def test_an_unreadable_fork_point_is_an_external_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _base(tmp_path, UNUSED_KEY)

    assert run_gate(repo, repo / BASELINE_RELPATH, "--base-ref", "no-such-ref") == 3
    assert "FORK POINT UNREADABLE" in capsys.readouterr().err


def test_without_a_base_ref_the_gate_says_the_growth_check_did_not_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    baseline = commit_baseline(repo, UNUSED_KEY)

    assert run_gate(repo, baseline) == 0
    assert "baseline growth NOT CHECKED" in capsys.readouterr().out


def test_without_a_base_ref_the_gate_falls_back_to_main(tmp_path: Path) -> None:
    repo = _base(tmp_path, UNUSED_KEY)
    git(repo, "checkout", "-q", "-b", "feature")
    git(repo, "branch", "-f", "main", "base")
    add_file(repo, "scripts/other.py", OTHER)
    commit_baseline(repo, UNUSED_KEY, OTHER_KEY)

    assert run_gate(repo, repo / BASELINE_RELPATH) == 1


def test_a_baseline_outside_the_repo_is_a_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _base_in(tmp_path)
    outside = tmp_path / "baseline.txt"
    outside.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")

    assert run_gate(repo, outside, "--base-ref", "base") == 2
    assert "outside" in capsys.readouterr().err


def _base_in(tmp_path: Path) -> Path:
    """Build the ``base`` repo in a subdirectory so a sibling file lies outside it."""
    inner = tmp_path / "repo"
    inner.mkdir()
    return _base(inner, UNUSED_KEY)
