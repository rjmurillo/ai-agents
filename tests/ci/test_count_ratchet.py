from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.ci import count_ratchet


def test_chunk_respects_argv_budget():
    paths = [f"{'x' * 99}{index}.py" for index in range(500)]
    batches = count_ratchet.chunk(paths, budget=1000)
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
    batches = count_ratchet.chunk(paths, budget=46)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 46 for batch in batches)
    # Two per batch fits the byte budget; a character measure would pack three.
    assert max(len(batch) for batch in batches) == 2


def test_single_path_longer_than_budget_still_scanned():
    # A path larger than the whole budget must not be silently dropped.
    oversized = "y" * 5000 + ".py"
    assert count_ratchet.chunk([oversized], budget=100) == [[oversized]]


def test_tracked_files_returns_none_when_git_fails(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a repo\n")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) is None


def test_tracked_files_drops_the_nul_terminator(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="a.py\0b.py\0", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) == ["a.py", "b.py"]


def test_read_baseline_rejects_a_non_integer(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("not a number\n", encoding="utf-8")
    assert count_ratchet.read_baseline(path) is None


def test_read_baseline_returns_none_when_missing(tmp_path):
    assert count_ratchet.read_baseline(tmp_path / "absent.txt") is None


# ---------------------------------------------------------------------------
# lister parameter behavior (issue #3902)
# ---------------------------------------------------------------------------


def _make_args(tmp_path: Path, baseline_value: int) -> argparse.Namespace:
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(f"{baseline_value}\n", encoding="utf-8")
    return argparse.Namespace(
        baseline=baseline_file,
        repo_root=tmp_path,
        update=False,
        base_ref=None,
    )


def test_lister_called_and_printed_on_regression(tmp_path, capsys):
    """Violations are printed to stderr when lister is provided and a regression fires."""
    args = _make_args(tmp_path, baseline_value=5)
    violations = ["file1.py: use X", "file2.py: avoid Y"]

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 7,  # 7 > 5 => regression
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root: violations,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "file1.py: use X" in err
    assert "file2.py: avoid Y" in err


def test_lister_not_called_on_ok(tmp_path, capsys):
    """Lister is never called when there is no regression (count <= baseline)."""
    args = _make_args(tmp_path, baseline_value=10)
    called: list[bool] = []

    def _recording_lister(_root: Path) -> list[str] | None:
        called.append(True)
        return ["oops"]

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 10,  # equal to baseline => ok
        scan_error="scan failed",
        regression_advice="fix it",
        lister=_recording_lister,
    )

    assert rc == count_ratchet.EXIT_OK
    assert called == [], "lister must not be invoked when there is no regression"


def test_no_lister_regression_has_no_violation_list(tmp_path, capsys):
    """When lister is None, a regression message appears but no violation lines."""
    args = _make_args(tmp_path, baseline_value=5)

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 8,  # 8 > 5 => regression
        scan_error="scan failed",
        regression_advice="fix it",
        lister=None,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "REGRESSION" in err
    assert "Current violations" not in err


def test_lister_truncates_at_40_violations(tmp_path, capsys):
    """Only the first 40 violations are printed; the remainder is summarised."""
    args = _make_args(tmp_path, baseline_value=5)
    violations = [f"file{i}.py: issue" for i in range(50)]

    count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 55,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root: violations,
    )

    err = capsys.readouterr().err
    assert "file0.py: issue" in err
    assert "file39.py: issue" in err
    assert "file40.py: issue" not in err
    assert "10 more" in err


def test_lister_returning_none_does_not_crash(tmp_path, capsys):
    """If lister returns None, no violation list is printed and the run still fails."""
    args = _make_args(tmp_path, baseline_value=5)

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 7,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root: None,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "REGRESSION" in err
    assert "Current violations" not in err
