"""Tests for the unindexed-memory count ratchet (issue #4313).

The subprocess fake dispatches on the argument vector rather than on call
order, per ``.claude/rules/testing.md`` SHOULD 10: ``_collect`` calls the
validator and ``git ls-files``, and a call-order fake would keep passing if
those two calls were ever reordered or one were dropped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import memory_index_count_ratchet as ratchet

ATOMIC_WARNING = "git/rebase-costs.md: not referenced by any domain index"
INDEX_WARNING = "skills-copilot-index.md: not referenced by memory-index.md"
UNTRACKED_WARNING = "scratch/draft.md: not referenced by any domain index"


def _write_baseline(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "memory_index_count_baseline.txt"
    path.write_text(value + "\n", encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    """A tree with the validator present, so ``_warning_lines`` reaches it."""
    validator = tmp_path / "scripts" / "validate_memory_tier.py"
    validator.parent.mkdir(parents=True, exist_ok=True)
    validator.write_text("", encoding="utf-8")
    return tmp_path


def _fake(
    warnings: tuple[str, ...] = (ATOMIC_WARNING,),
    tracked: tuple[str, ...] = ("git/rebase-costs.md",),
    validator_rc: int = 0,
    git_rc: int = 0,
    extra_stdout: str = "",
):
    """subprocess.run stub dispatched on argv, never on call order."""

    def _run(cmd, **kwargs):
        argv = [str(part) for part in cmd]
        if "ls-files" in argv:
            stdout = "".join(f".serena/memories/{name}\0" for name in tracked)
            return subprocess.CompletedProcess(cmd, git_rc, stdout=stdout, stderr="")
        if str(ratchet._VALIDATOR) in argv:
            body = "".join(f"WARNING: {w}\n" for w in warnings) + extra_stdout
            return subprocess.CompletedProcess(cmd, validator_rc, stdout=body, stderr="")
        raise AssertionError(f"unexpected subprocess call: {argv}")

    return _run


class TestCurrentCount:
    def test_counts_one_unindexed_atomic_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake())
        assert ratchet.current_count(_repo(tmp_path)) == 1

    def test_counts_both_warning_shapes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreferenced domain index counts too, not only atomic files.

        Discriminating input: an implementation that kept only subjects
        containing a directory separator would return 1 here.
        """
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(
                warnings=(ATOMIC_WARNING, INDEX_WARNING),
                tracked=("git/rebase-costs.md", "skills-copilot-index.md"),
            ),
        )
        assert ratchet.current_count(_repo(tmp_path)) == 2

    def test_returns_zero_when_every_memory_is_indexed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake(warnings=()))
        assert ratchet.current_count(_repo(tmp_path)) == 0

    def test_ignores_output_lines_that_are_not_warnings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(extra_stdout="Scanned 896 files\nSummary: 1 warning\n"),
        )
        assert ratchet.current_count(_repo(tmp_path)) == 1

    def test_untracked_memory_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scratch memory on one disk must not count against that contributor.

        ``validate_orphan_atomics`` walks the tree with ``rglob``, so without
        the tracked filter this returns 2 locally and 1 in CI, which is the
        phantom-count failure ``ruff_count_ratchet.py`` was written to avoid.
        """
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(
                warnings=(ATOMIC_WARNING, UNTRACKED_WARNING),
                tracked=("git/rebase-costs.md",),
            ),
        )
        assert ratchet.current_count(_repo(tmp_path)) == 1

    def test_tracked_filter_is_load_bearing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The isolating control for the test above: track it and it counts."""
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(
                warnings=(ATOMIC_WARNING, UNTRACKED_WARNING),
                tracked=("git/rebase-costs.md", "scratch/draft.md"),
            ),
        )
        assert ratchet.current_count(_repo(tmp_path)) == 2

    def test_returns_none_when_validator_reports_a_structural_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-zero exit is an error, not a warning count.

        Returning 0 here would let ``--update`` write a zero baseline and
        permanently disarm the gate.
        """
        monkeypatch.setattr(subprocess, "run", _fake(validator_rc=1))
        assert ratchet.current_count(_repo(tmp_path)) is None

    def test_returns_none_when_validator_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake())
        assert ratchet.current_count(tmp_path) is None

    def test_returns_none_when_validator_cannot_be_launched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(cmd, **kwargs):
            raise OSError("no exec")

        monkeypatch.setattr(subprocess, "run", _boom)
        assert ratchet.current_count(_repo(tmp_path)) is None

    def test_returns_none_when_git_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake(git_rc=128))
        assert ratchet.current_count(_repo(tmp_path)) is None

    def test_scan_does_not_pass_ci_to_the_validator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--ci collapses "many warnings" and "real error" into the same exit 1.

        The counter distinguishes them by exit code, so the flag must stay off.
        """
        seen: list[list[str]] = []

        def _record(cmd, **kwargs):
            argv = [str(part) for part in cmd]
            seen.append(argv)
            return _fake()(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", _record)
        ratchet.current_count(_repo(tmp_path))
        validator_calls = [a for a in seen if str(ratchet._VALIDATOR) in a]
        assert validator_calls, "the validator was never invoked"
        assert all("--ci" not in argv for argv in validator_calls)


class TestListViolations:
    def test_branch_touched_violations_are_listed_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``run`` caps the printed list at 40 lines and the repo carries 425.

        Emission order alone would bury the branch's own violation below the cap.
        """
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(
                warnings=(ATOMIC_WARNING, INDEX_WARNING),
                tracked=("git/rebase-costs.md", "skills-copilot-index.md"),
            ),
        )
        violations = ratchet.list_violations(
            _repo(tmp_path),
            frozenset({".serena/memories/skills-copilot-index.md"}),
        )
        assert violations == [INDEX_WARNING, ATOMIC_WARNING]

    def test_order_is_unchanged_without_priority_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake(
                warnings=(ATOMIC_WARNING, INDEX_WARNING),
                tracked=("git/rebase-costs.md", "skills-copilot-index.md"),
            ),
        )
        assert ratchet.list_violations(_repo(tmp_path)) == [ATOMIC_WARNING, INDEX_WARNING]

    def test_returns_none_when_the_scan_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake(validator_rc=2))
        assert ratchet.list_violations(_repo(tmp_path)) is None


class TestConstants:
    def test_baseline_filename_is_canonical(self) -> None:
        assert ratchet._BASELINE_PATH.name == "memory_index_count_baseline.txt"

    def test_validator_path_matches_the_lefthook_job(self) -> None:
        assert str(ratchet._VALIDATOR) == "scripts/validate_memory_tier.py"


class TestMain:
    def test_ok_when_count_equals_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 425)
        assert ratchet.main([]) == count_ratchet.EXIT_OK
        assert "OK" in capsys.readouterr().out

    def test_regression_when_a_new_unindexed_memory_appears(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 426)
        monkeypatch.setattr(ratchet, "list_violations", lambda *_: [ATOMIC_WARNING])
        assert ratchet.main([]) == count_ratchet.EXIT_REGRESSION
        err = capsys.readouterr().err
        assert "REGRESSION" in err
        assert ATOMIC_WARNING in err

    def test_indexing_a_memory_passes_without_updating(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 424)
        assert ratchet.main([]) == count_ratchet.EXIT_OK
        assert baseline.read_text(encoding="utf-8").strip() == "425"

    def test_update_lowers_the_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 400)
        assert ratchet.main(["--update"]) == count_ratchet.EXIT_OK
        assert baseline.read_text(encoding="utf-8").strip() == "400"

    def test_update_never_raises_the_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 426)
        monkeypatch.setattr(ratchet, "list_violations", lambda *_: [])
        ratchet.main(["--update"])
        assert baseline.read_text(encoding="utf-8").strip() == "425"

    def test_config_error_when_baseline_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", tmp_path / "absent.txt")
        assert ratchet.main([]) == count_ratchet.EXIT_CONFIG

    def test_external_error_when_the_scan_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "425")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: None)
        assert ratchet.main([]) == count_ratchet.EXIT_EXTERNAL

    def test_cli_entry_point_runs_against_the_real_repo(self) -> None:
        """End to end, no fakes: the shipped baseline must match the real tree."""
        repo_root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [sys.executable, "scripts/ci/memory_index_count_ratchet.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == count_ratchet.EXIT_OK, proc.stdout + proc.stderr
