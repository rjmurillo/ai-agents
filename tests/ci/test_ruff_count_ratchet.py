"""Tests for the whole-repo ruff count ratchet (issue #2993)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_count_ratchet as ratchet

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_scan(
    returncode: int,
    violation_lines: int,
    *,
    tracked: tuple[str, ...] = ("pkg/mod.py",),
    git_returncode: int = 0,
    ruff_stdout: str | None = None,
):
    """subprocess.run stand-in for every leg of the scan.

    ``git ls-files -z`` returns ``tracked`` NUL-joined; every ruff invocation
    returns ``violation_lines`` json-lines rows unless ``ruff_stdout``
    overrides them. Violations are emitted once per ruff call, so a
    multi-batch expectation must size ``tracked`` accordingly.
    """

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            stdout = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, git_returncode, stdout=stdout, stderr="")
        stdout = (
            ruff_stdout
            if ruff_stdout is not None
            else "".join('{"code":"E501"}\n' for _ in range(violation_lines))
        )
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def test_clean_tree_counts_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(0, 0))
    assert ratchet.current_count(tmp_path) == 0


def test_ruff_crash_yields_no_count(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(2, 0))
    assert ratchet.current_count(tmp_path) is None


def test_git_failure_yields_no_count(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408, git_returncode=128))
    assert ratchet.current_count(tmp_path) is None


def test_main_maps_an_unmeasurable_count_to_exit_3(monkeypatch):
    monkeypatch.setattr(ratchet, "current_count", lambda _root: None)
    assert ratchet.main(["--base-ref", "HEAD"]) == ratchet.EXIT_EXTERNAL


def test_no_tracked_python_files_counts_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 99, tracked=()))
    assert ratchet.current_count(tmp_path) == 0


def test_chunked_batches_sum_instead_of_overwrite(tmp_path, monkeypatch):
    # Two batches x 5 violations each must total 10, not 5. Guards the
    # accumulate-across-batches contract the Windows argv ceiling forces.
    long_a = "a" * 20000 + ".py"
    long_b = "b" * 20000 + ".py"
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 5, tracked=(long_a, long_b)))
    assert ratchet.current_count(tmp_path) == 10


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_untracked_worktree_violations_are_not_counted(tmp_path):
    """The #2993 regression: an untracked nested tree must not inflate the count.

    A real repo with one tracked clean file plus an untracked directory full of
    violations. ``ruff check .`` would walk the untracked tree; the tracked-file
    scan must report zero.
    """
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\n[tool.ruff.lint]\nselect = ["E", "F"]\n',
        encoding="utf-8",
    )
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "t"],
        ["git", "add", "pkg/clean.py", "pyproject.toml"],
        ["git", "commit", "-qm", "init"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)

    shadow = repo / "nested-worktree"
    shadow.mkdir()
    (shadow / "dirty.py").write_text("import os\nimport sys\n", encoding="utf-8")

    assert ratchet.current_count(repo) == 0


def test_scan_scope_includes_every_extension_ruff_lints(tmp_path, monkeypatch):
    # A PR adding only a faulty stub or notebook must not slip past a
    # Python-only gate. The repo tracks none of either today, so this pins the
    # scope rather than the count.
    seen: list[list[str]] = []

    def _run(cmd, **kwargs):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    ratchet.current_count(tmp_path)
    assert seen[0][seen[0].index("--") + 1 :] == ["*.py", "*.pyi", "*.ipynb"]


def test_ruff_io_error_is_not_counted_as_a_violation(tmp_path, monkeypatch):
    # ruff reports a missing or unreadable path as an ordinary E902 diagnostic
    # on exit 1. Counting it as lint debt turns a stale index or a sparse
    # checkout into a phantom count change.
    io_error = '{"code":"E902","filename":"gone.py","message":"No such file"}\n'
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, ruff_stdout=io_error))
    assert ratchet.current_count(tmp_path) is None


def test_unparseable_diagnostic_still_counts(tmp_path, monkeypatch):
    # The count is the metric this gate defends, so a line ruff emitted that
    # this script cannot parse must not silently lower it.
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, ruff_stdout="not json\n"))
    assert ratchet.current_count(tmp_path) == 1


def test_main_without_base_ref_is_a_config_error(capsys):
    assert ratchet.main([]) == ratchet.EXIT_CONFIG
    captured = capsys.readouterr()
    assert "--base-ref" in captured.err + captured.out


def test_main_wires_this_ratchet_into_the_base_derived_run(monkeypatch):
    seen: dict = {}

    def _run(args, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(ratchet, "run", _run)
    assert ratchet.main(["--base-ref", "origin/main"]) == 0
    assert seen["label"] == "ruff count ratchet"
    assert seen["introduced_by"] == ratchet._SCRIPT
    assert seen["counter"] is ratchet.current_count


def test_script_marker_names_a_tracked_file():
    assert (REPO_ROOT / ratchet._SCRIPT).is_file()


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_end_to_end_against_head_passes_on_the_real_repo():
    assert ratchet.main(["--base-ref", "HEAD", "--repo-root", str(REPO_ROOT)]) == ratchet.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
