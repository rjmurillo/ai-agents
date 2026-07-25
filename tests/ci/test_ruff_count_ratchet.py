"""Tests for the whole-repo ruff count ratchet (issue #2993)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_count_ratchet as ratchet


def _fake_scan(
    returncode: int,
    violation_lines: int,
    *,
    tracked: tuple[str, ...] = ("pkg/mod.py",),
    git_returncode: int = 0,
    base_baseline: str | None = None,
    ruff_stdout: str | None = None,
):
    """subprocess.run stand-in for every leg of the scan.

    ``git ls-files -z`` returns ``tracked`` NUL-joined; ``git show`` returns
    ``base_baseline``; every ruff invocation returns ``violation_lines``
    json-lines rows unless ``ruff_stdout`` overrides them. Violations are
    emitted once per ruff call, so a multi-batch expectation must size
    ``tracked`` accordingly.
    """

    def _run(cmd, **kwargs):  # noqa: ANN001, ANN003
        if cmd[0] == "git" and "show" in cmd:
            rc = 0 if base_baseline is not None else 128
            return subprocess.CompletedProcess(
                cmd, rc, stdout=(base_baseline or ""), stderr=""
            )
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


def _write_baseline(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "ruff_count_baseline.txt"
    path.write_text(value, encoding="utf-8")
    return path


def test_count_equal_to_baseline_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_count_above_baseline_is_regression(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 409))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_REGRESSION


def test_count_below_baseline_passes_without_updating(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 400))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "408"


def test_count_below_baseline_with_update_lowers_baseline(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(0, 400))
    rc = ratchet.main(
        ["--baseline", str(baseline), "--repo-root", str(tmp_path), "--update"]
    )
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "400"


def test_clean_tree_zero_count_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "0")
    monkeypatch.setattr(subprocess, "run", _fake_scan(0, 0))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_missing_baseline_is_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408))
    rc = ratchet.main(
        ["--baseline", str(tmp_path / "absent.txt"), "--repo-root", str(tmp_path)]
    )
    assert rc == ratchet.EXIT_CONFIG


def test_malformed_baseline_is_config_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "not-a-number")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


def test_ruff_crash_is_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(2, 0))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_git_failure_is_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408, git_returncode=128))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_no_tracked_python_files_counts_zero(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "0")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 99, tracked=()))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_chunked_batches_sum_instead_of_overwrite(tmp_path, monkeypatch):
    # Two batches x 5 violations each must total 10, not 5. Guards the
    # accumulate-across-batches contract the Windows argv ceiling forces.
    long_a = "a" * 20000 + ".py"
    long_b = "b" * 20000 + ".py"
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 5, tracked=(long_a, long_b)))
    assert ratchet.current_count(tmp_path) == 10


def test_chunk_respects_argv_budget():
    paths = [f"{'x' * 99}{index}.py" for index in range(500)]
    batches = ratchet._chunk(paths, budget=1000)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 1000 for batch in batches)
    assert all(batch for batch in batches)


def test_chunk_measures_bytes_not_characters():
    # A non-ASCII path costs more argv than it has characters. Measuring
    # characters would pack batches over the ceiling the budget exists to
    # respect. Each name here is 13 characters but 22 UTF-8 bytes.
    stem = "\u00e9" * 9
    paths = [f"{stem}{index}.py" for index in range(10)]
    assert len(paths[0]) == 13
    assert len(paths[0].encode("utf-8")) == 22
    batches = ratchet._chunk(paths, budget=46)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 46 for batch in batches)
    # Two per batch fits the byte budget; a character measure would pack three.
    assert max(len(batch) for batch in batches) == 2


def test_single_path_longer_than_budget_still_scanned():
    # A path larger than the whole budget must not be silently dropped.
    oversized = "y" * 5000 + ".py"
    assert ratchet._chunk([oversized], budget=100) == [[oversized]]


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

    def _run(cmd, **kwargs):  # noqa: ANN001, ANN003
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    ratchet.tracked_python_files(tmp_path)
    assert seen[0][seen[0].index("--") + 1 :] == ["*.py", "*.pyi", "*.ipynb"]


def test_ruff_io_error_is_not_counted_as_a_violation(tmp_path, monkeypatch):
    # ruff reports a missing or unreadable path as an ordinary E902 diagnostic
    # on exit 1. Counting it as lint debt turns a stale index or a sparse
    # checkout into a phantom count change.
    baseline = _write_baseline(tmp_path, "408")
    io_error = '{"code":"E902","filename":"gone.py","message":"No such file"}\n'
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, ruff_stdout=io_error))
    argv = ["--repo-root", str(tmp_path), "--baseline", str(baseline)]
    assert ratchet.main(argv) == ratchet.EXIT_EXTERNAL


def test_unparseable_diagnostic_still_counts(tmp_path, monkeypatch):
    # The count is the metric this gate defends, so a line ruff emitted that
    # this script cannot parse must not silently lower it.
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, ruff_stdout="not json\n"))
    assert ratchet.current_count(tmp_path) == 1


def test_raising_the_baseline_is_a_regression(tmp_path, monkeypatch):
    # Without this the ratchet is one-sided: raising the baseline in the same
    # PR that adds the violations passes as an improvement.
    baseline = _write_baseline(tmp_path, "500")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 500, base_baseline="408"))
    code = ratchet.main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--base-ref", "origin/main"]
    )
    assert code == 1


def test_lowering_the_baseline_is_allowed(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "400")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 400, base_baseline="408"))
    code = ratchet.main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--base-ref", "origin/main"]
    )
    assert code == 0


def test_unreadable_base_ref_is_external_error(tmp_path, monkeypatch):
    # A shallow clone that cannot reach the base ref must fail loudly rather
    # than silently skip the one-directional check.
    baseline = _write_baseline(tmp_path, "408")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 408, base_baseline=None))
    code = ratchet.main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--base-ref", "origin/main"]
    )
    assert code == 3


def test_baseline_outside_the_repo_root_is_rejected(tmp_path):
    outside = tmp_path / "elsewhere" / "baseline.txt"
    outside.parent.mkdir()
    outside.write_text("1\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    assert ratchet.baseline_at_ref(root, "origin/main", outside) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
