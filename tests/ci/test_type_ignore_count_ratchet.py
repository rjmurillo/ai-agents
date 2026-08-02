"""Tests for the type-ignore count ratchet (issue #4039)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import type_ignore_count_ratchet as ratchet


def _write_baseline(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "type_ignore_count_baseline.txt"
    path.write_text(value + "\n", encoding="utf-8")
    return path


def _fake_git(files: tuple[str, ...] = ("pkg/mod.py",), git_rc: int = 0):
    """subprocess.run stub that returns a tracked-file list from git ls-files."""

    def _run(cmd, **kwargs):
        stdout = "\0".join(files) + ("\0" if files else "")
        return subprocess.CompletedProcess(cmd, git_rc, stdout=stdout, stderr="")

    return _run


# --- unit tests for current_count -----------------------------------------


class TestCurrentCount:
    def test_counts_type_ignore_in_single_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        py = tmp_path / "mod.py"
        py.write_text(
            "x: int = 'hi'  # type: ignore[assignment]\ny = 1\nz: str = 2  # type: ignore\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 2

    def test_counts_across_multiple_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("x = y  # type: ignore[name-defined]\n", encoding="utf-8")
        b.write_text("a = b  # type: ignore\n", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git((str(a), str(b))))
        assert ratchet.current_count(tmp_path) == 2

    def test_returns_zero_when_no_type_ignores(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        py = tmp_path / "clean.py"
        py.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 0

    def test_returns_zero_for_empty_file_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(()))
        assert ratchet.current_count(tmp_path) == 0

    def test_returns_none_when_git_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(git_rc=128))
        assert ratchet.current_count(tmp_path) is None

    def test_returns_none_when_file_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(("/nonexistent/path.py",)))
        assert ratchet.current_count(tmp_path) is None

    def test_ignores_partial_matches(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        py = tmp_path / "mod.py"
        py.write_text(
            "# noqa: type-ignore-something\n"  # inline test string, not a mypy annotation
            "# type-ignore\n"  # hyphen before "ignore", not a mypy annotation
            "x: int = 'hi'  # type: ignore\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(subprocess, "run", _fake_git((str(py),)))
        assert ratchet.current_count(tmp_path) == 1


class TestConstants:
    def test_py_globs_targets_python_files(self) -> None:
        """_PY_GLOBS must target .py files; mutation to another extension must be detected."""
        assert ratchet._PY_GLOBS == ("*.py",)

    def test_baseline_filename_is_correct(self) -> None:
        """Baseline path must end with the canonical filename."""
        assert ratchet._BASELINE_PATH.name == "type_ignore_count_baseline.txt"


# --- integration tests for main() -----------------------------------------


class TestMain:
    def test_ok_when_count_equals_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 5)
        rc = ratchet.main([])
        assert rc == count_ratchet.EXIT_OK
        assert "OK" in capsys.readouterr().out

    def test_regression_when_count_exceeds_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 6)
        rc = ratchet.main([])
        assert rc == count_ratchet.EXIT_REGRESSION

    def test_count_below_baseline_passes_without_update(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #4171: lower counts pass without rewriting shared baseline."""
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 4)
        rc = ratchet.main([])
        assert rc == count_ratchet.EXIT_OK
        captured = capsys.readouterr()
        assert "<= baseline" in captured.out
        assert "BASELINE STALE" not in captured.err

    def test_update_lowers_baseline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 3)
        rc = ratchet.main(["--update"])
        assert rc == count_ratchet.EXIT_OK
        assert baseline.read_text(encoding="utf-8").strip() == "3"

    def test_update_does_not_raise_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 5)
        ratchet.main(["--update"])
        assert baseline.read_text(encoding="utf-8").strip() == "5"

    def test_config_error_when_baseline_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "no_baseline.txt"
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", missing)
        rc = ratchet.main([])
        assert rc == count_ratchet.EXIT_CONFIG

    def test_external_error_when_scan_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "5")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: None)
        rc = ratchet.main([])
        assert rc == count_ratchet.EXIT_EXTERNAL

    def test_base_ref_blocks_raised_allowance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A PR that raises the baseline vs origin/main must be blocked."""
        baseline = _write_baseline(tmp_path, "10")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)

        call_count = 0

        def _fake_git_with_base(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "rev-parse" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "ls-tree" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="100644 blob abc\tbaseline.txt\n", stderr=""
                )
            if "show" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="5\n", stderr="")
            stdout = "\0".join(("mod.py",)) + "\0"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_git_with_base)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 10)
        rc = ratchet.main(["--base-ref", "origin/main"])
        assert rc == count_ratchet.EXIT_REGRESSION

    def test_base_ref_stale_branch_message_uses_count(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        baseline = _write_baseline(tmp_path, "10")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)

        def _fake_git_with_base(cmd, **kwargs):
            if "rev-parse" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "ls-tree" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="100644 blob abc\tbaseline.txt\n", stderr=""
                )
            if "show" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="5\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="mod.py\0", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_git_with_base)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 4)
        rc = ratchet.main(["--base-ref", "origin/main"])
        captured = capsys.readouterr()
        assert rc == count_ratchet.EXIT_REGRESSION
        assert "BRANCH BEHIND" in captured.err
        assert "BASELINE RAISED" not in captured.err
