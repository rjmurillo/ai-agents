"""Tests for ``scripts/ci/base_derived_ratchet.py`` (issue #5363).

Every test drives a real git repository. The counter is a fake that reads an
integer from ``count.txt`` in whatever tree it is handed, so the fork tree, the
branch tree and a dirty working tree can each report a different number and the
test can say which one the ceiling came from.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import base_derived_ratchet as brd

MARKER = "scripts/ci/marker_ratchet.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(repo: Path, *argv: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env=env,
    )
    return proc.stdout.strip()


def _commit(repo: Path, count: int, *, marker: bool = True, message: str = "c") -> None:
    (repo / "count.txt").write_text(f"{count}\n", encoding="utf-8")
    if marker:
        path = repo / MARKER
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# marker\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--allow-empty", "-qm", message)


def _init(path: Path, count: int, *, marker: bool = True) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    _commit(path, count, marker=marker)
    return path


def _counter(root: Path) -> int | None:
    try:
        return int((root / "count.txt").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _run(repo: Path, *, base_ref: str | None = "main", **overrides: object) -> int:
    args = brd.build_parser("test").parse_args(
        ["--repo-root", str(repo), *(["--base-ref", base_ref] if base_ref else [])]
    )
    kwargs: dict[str, Any] = {
        "label": "fake ratchet",
        "counter": _counter,
        "scan_error": "fake scan failed",
        "regression_advice": "Remove the violations.",
        "introduced_by": MARKER,
    }
    kwargs.update(overrides)
    return brd.run(args, **kwargs)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _init(tmp_path / "repo", 10)


def _branch(repo: Path, count: int) -> None:
    _git(repo, "checkout", "-qb", "topic")
    _commit(repo, count, message="topic")


def test_a_branch_at_the_merge_base_count_passes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 10)
    assert _run(repo) == brd.EXIT_OK
    assert "count == merge base 10" in capsys.readouterr().out


def test_a_branch_below_the_merge_base_passes_and_reports_the_gain(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 7)
    assert _run(repo) == brd.EXIT_OK
    assert "3 below the merge base (10)" in capsys.readouterr().out


def test_a_branch_above_the_merge_base_regresses(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 12)
    assert _run(repo) == brd.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "REGRESSION. 12 violations > 10 at the merge base (+2)" in err
    assert "Remove the violations." in err


def test_a_ceiling_lowered_on_main_after_the_fork_does_not_block_the_branch(
    repo: Path,
) -> None:
    """The BEHIND BASE shape: main improved, the branch holds the fork count."""
    _branch(repo, 10)
    _git(repo, "checkout", "-q", "main")
    _commit(repo, 4, message="main improves")
    _git(repo, "checkout", "-q", "topic")
    assert _run(repo) == brd.EXIT_OK


def test_the_ceiling_is_the_committed_fork_tree_not_the_working_tree(
    repo: Path,
) -> None:
    _branch(repo, 10)
    (repo / "count.txt").write_text("99\n", encoding="utf-8")
    assert brd.measure_commit(repo, "main", _counter) == 10


def test_a_missing_base_ref_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 10)
    assert _run(repo, base_ref=None) == brd.EXIT_CONFIG
    assert "--base-ref is required" in capsys.readouterr().err


def test_a_fork_point_without_the_ratchet_is_the_bootstrap_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init(tmp_path / "boot", 1, marker=False)
    _git(repo, "checkout", "-qb", "topic")
    _commit(repo, 500, marker=True, message="introduce the ratchet")
    assert _run(repo) == brd.EXIT_OK
    out = capsys.readouterr().out
    assert "bootstrap" in out
    assert MARKER in out


def test_a_branch_that_introduces_a_higher_count_after_bootstrap_still_regresses(
    repo: Path,
) -> None:
    """Edge: bootstrap is decided by the marker, not by a count difference."""
    _branch(repo, 11)
    assert _run(repo) == brd.EXIT_REGRESSION


def test_unrelated_history_has_no_fork_point(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "--orphan", "island")
    _commit(repo, 10, message="island")
    assert _run(repo) == brd.EXIT_EXTERNAL
    err = capsys.readouterr().err
    assert "FORK POINT UNREADABLE" in err
    assert "shares no history" in err


def test_a_shallow_clone_gets_the_fetch_remedy(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "--orphan", "island")
    _commit(repo, 10, message="island")
    monkeypatch.setattr(brd, "is_shallow_repository", lambda _root: True)
    assert _run(repo) == brd.EXIT_EXTERNAL
    assert "git fetch --unshallow" in capsys.readouterr().err


def test_a_counter_that_fails_on_the_branch_is_an_external_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 10)
    assert _run(repo, counter=lambda _root: None) == brd.EXIT_EXTERNAL
    assert "fake scan failed" in capsys.readouterr().err


def test_a_counter_that_fails_only_on_the_fork_tree_is_an_external_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ceiling could not be measured, so it must never read as a pass."""
    _branch(repo, 10)

    def flaky(root: Path) -> int | None:
        return None if root.name.startswith("base-derived-ratchet-") else 10

    assert _run(repo, counter=flaky) == brd.EXIT_EXTERNAL
    assert "could not measure the merge base" in capsys.readouterr().err


def test_an_unresolvable_commit_cannot_be_measured(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert brd.measure_commit(repo, "no-such-ref", _counter) is None
    assert "could not resolve the tree" in capsys.readouterr().err


def test_measuring_leaves_no_scratch_directory(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch_parent = tmp_path / "scratch-parent"
    scratch_parent.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch_parent))
    assert brd.measure_commit(repo, "main", _counter) == 10
    assert list(scratch_parent.iterdir()) == []


def test_a_failed_scratch_cleanup_is_not_a_measurement(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(brd, "remove_tree", lambda _path, _label: "cleanup failed: denied")
    assert brd.measure_commit(repo, "main", _counter) is None
    assert "cleanup failed: denied" in capsys.readouterr().err


def test_a_foreign_git_dir_in_the_environment_does_not_redirect_the_read(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #4914: an exported GIT_DIR outranks ``-C`` unless it is stripped."""
    other = _init(tmp_path / "other", 77)
    _branch(repo, 10)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert _run(repo) == brd.EXIT_OK


def test_violations_are_listed_and_capped_on_regression(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 12)
    lister = lambda _root, _changed: [f"v{i}" for i in range(45)]  # noqa: E731
    assert _run(repo, lister=lister) == brd.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "Current violations:" in err
    assert "v39" in err
    assert "v40" not in err
    assert "... and 5 more" in err


def test_an_empty_violation_list_prints_nothing_extra(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 12)
    assert _run(repo, lister=lambda _root, _changed: []) == brd.EXIT_REGRESSION
    assert "Current violations:" not in capsys.readouterr().err


def test_a_lister_is_not_called_when_the_branch_passes(repo: Path) -> None:
    _branch(repo, 10)

    def boom(_root: Path, _changed: frozenset[str]) -> list[str]:
        raise AssertionError("lister must only run on regression")

    assert _run(repo, lister=boom) == brd.EXIT_OK


def test_introduced_at_is_false_for_a_typoed_ref_so_the_caller_measures(
    repo: Path,
) -> None:
    """Fail closed: a git error must not read as the bootstrap case."""
    assert brd.introduced_at(repo, "no-such-ref", MARKER) is False
    assert brd.introduced_at(repo, "main", MARKER) is False
    assert brd.introduced_at(repo, "main", "scripts/ci/absent.py") is True


def test_the_parser_requires_no_baseline_and_offers_no_update_flag() -> None:
    parser = brd.build_parser("x")
    dests = {action.dest for action in parser._actions}
    assert {"repo_root", "base_ref"} <= dests
    assert "baseline" not in dests
    assert "update" not in dests
