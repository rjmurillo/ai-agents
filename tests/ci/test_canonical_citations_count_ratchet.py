"""Tests for the uncited mirror-claim count ratchet (issue #5636, D11).

Intended exception: the count may fall and the baseline may be lowered. Forbidden
silent pass: a new uncited mirror-claim, an unreadable file, a failed git listing,
or a raised baseline reads as green.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import canonical_citations_count_ratchet as ratchet
from scripts.ci import count_ratchet
from scripts.validation import check_canonical_citations as checker
from tests.ci.ratchet_test_helpers import make_baseline_writer

REPO_ROOT = Path(__file__).resolve().parents[2]

_write_baseline = make_baseline_writer(
    "canonical_citations_count_baseline.txt", trailing_newline=True
)

UNCITED = '"""This validator matches the upstream contract."""\n'
CITED = '"""This validator matches the contract in scripts/validation/foo.py."""\n'
NO_CLAIM = '"""Plain module."""\n'


def _fake_git(files: tuple[str, ...], git_rc: int = 0):
    def _run(cmd, **kwargs):
        stdout = "\0".join(files) + ("\0" if files else "")
        return subprocess.CompletedProcess(cmd, git_rc, stdout=stdout, stderr="")

    return _run


def _put(root: Path, rel: str, text: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


class TestCurrentCount:
    def test_counts_an_uncited_claim_in_each_scan_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rels = tuple(
            _put(tmp_path, f"{root}m.py", UNCITED)
            for root in (
                ".claude/hooks/",
                "scripts/validation/",
                "build/scripts/",
                ".claude/skills/x/",
            )
        )
        monkeypatch.setattr(subprocess, "run", _fake_git(rels))
        assert ratchet.current_count(tmp_path) == 4

    def test_a_cited_claim_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rel = _put(tmp_path, "scripts/validation/a.py", CITED)
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        assert ratchet.current_count(tmp_path) == 0

    def test_a_file_with_no_claim_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rel = _put(tmp_path, "scripts/validation/a.py", NO_CLAIM)
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        assert ratchet.current_count(tmp_path) == 0

    def test_a_file_outside_the_scan_roots_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rel = _put(tmp_path, "scripts/ci/a.py", UNCITED)
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        assert ratchet.current_count(tmp_path) == 0

    def test_a_pycache_path_is_not_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rel = _put(tmp_path, "scripts/validation/__pycache__/a.py", UNCITED)
        monkeypatch.setattr(subprocess, "run", _fake_git((rel,)))
        assert ratchet.current_count(tmp_path) == 0

    def test_a_tracked_path_missing_from_disk_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(("scripts/validation/gone.py",)))
        assert ratchet.current_count(tmp_path) == 0

    def test_empty_listing_is_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git(()))
        assert ratchet.current_count(tmp_path) == 0

    def test_git_failure_is_none_not_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _fake_git((), git_rc=128))
        assert ratchet.current_count(tmp_path) is None

    def test_unreadable_file_is_none_not_a_violation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "scripts/validation/bad.py"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe not utf-8")
        monkeypatch.setattr(subprocess, "run", _fake_git(("scripts/validation/bad.py",)))
        assert ratchet.current_count(tmp_path) is None
        assert "could not read scripts/validation/bad.py" in capsys.readouterr().err

    def test_count_equals_the_strict_checker_on_the_same_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parity: the ratchet freezes the number STRICT_CANONICAL_CHECK=1 reports."""
        rels = (
            _put(tmp_path, "scripts/validation/u1.py", UNCITED),
            _put(tmp_path, "build/scripts/u2.py", UNCITED),
            _put(tmp_path, ".claude/skills/s/c.py", CITED),
            _put(tmp_path, ".claude/hooks/n.py", NO_CLAIM),
        )
        monkeypatch.setattr(subprocess, "run", _fake_git(rels))
        assert ratchet.current_count(tmp_path) == len(checker.collect_violations(tmp_path)) == 2


class TestShippedBaseline:
    def test_the_shipped_baseline_matches_the_tracked_tree(self) -> None:
        """An unrecorded improvement leaves slack for the next regression."""
        recorded = int(ratchet._BASELINE_PATH.read_text(encoding="utf-8").strip())
        assert ratchet.current_count(REPO_ROOT) == recorded

    def test_baseline_filename_and_scan_roots(self) -> None:
        assert ratchet._BASELINE_PATH.name == "canonical_citations_count_baseline.txt"
        assert ratchet._SCAN_ROOT_PREFIXES == (
            ".claude/hooks/",
            "scripts/validation/",
            "build/scripts/",
            ".claude/skills/",
        )

    def test_scan_roots_match_the_checker(self, tmp_path: Path) -> None:
        for prefix in ratchet._SCAN_ROOT_PREFIXES:
            (tmp_path / prefix).mkdir(parents=True)
        found = {p.relative_to(tmp_path).as_posix() + "/" for p in checker._scan_roots(tmp_path)}
        assert found == set(ratchet._SCAN_ROOT_PREFIXES)


class TestMain:
    def test_ok_when_count_equals_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", _write_baseline(tmp_path, "3"))
        monkeypatch.setattr(ratchet, "current_count", lambda _: 3)
        assert ratchet.main([]) == count_ratchet.EXIT_OK
        assert "OK" in capsys.readouterr().out

    def test_regression_when_count_exceeds_baseline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", _write_baseline(tmp_path, "3"))
        monkeypatch.setattr(ratchet, "current_count", lambda _: 4)
        assert ratchet.main([]) == count_ratchet.EXIT_REGRESSION
        assert "canonical-source-mirror.md" in capsys.readouterr().err + capsys.readouterr().out

    def test_lower_count_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", _write_baseline(tmp_path, "3"))
        monkeypatch.setattr(ratchet, "current_count", lambda _: 2)
        assert ratchet.main([]) == count_ratchet.EXIT_OK

    def test_update_lowers_the_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "3")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 1)
        assert ratchet.main(["--update"]) == count_ratchet.EXIT_OK
        assert baseline.read_text(encoding="utf-8").strip() == "1"

    def test_update_never_raises_the_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = _write_baseline(tmp_path, "3")
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", baseline)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 5)
        ratchet.main(["--update"])
        assert baseline.read_text(encoding="utf-8").strip() == "3"

    def test_missing_baseline_is_a_config_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", tmp_path / "absent.txt")
        assert ratchet.main([]) == count_ratchet.EXIT_CONFIG

    def test_scan_failure_is_an_external_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", _write_baseline(tmp_path, "3"))
        monkeypatch.setattr(ratchet, "current_count", lambda _: None)
        assert ratchet.main([]) == count_ratchet.EXIT_EXTERNAL

    def test_a_raised_baseline_is_blocked_against_the_base_ref(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ratchet, "_BASELINE_PATH", _write_baseline(tmp_path, "10"))

        def _fake(cmd, **kwargs):
            if "rev-parse" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "ls-tree" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="100644 blob abc\tbaseline.txt\n", stderr=""
                )
            if "show" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="3\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="mod.py\0", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake)
        monkeypatch.setattr(ratchet, "current_count", lambda _: 3)
        assert ratchet.main(["--base-ref", "origin/main"]) == count_ratchet.EXIT_REGRESSION
