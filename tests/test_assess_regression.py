"""Tests for assess.py regression gate (issue #4364).

Issue #4364: when ``--changed-only --base`` are both set, the gate must
compare the HEAD score against the BASE score (regression mode) rather than
against an absolute threshold (absolute mode).  A file that is below the
absolute threshold but was strictly improved by the diff must NOT block the
author.

Test strategy
-------------
- Unit-test ``check_regressions`` directly using hand-crafted
  ``FileAssessment`` instances whose values are literals, not derived from
  the code under test.
- Unit-test the ``main`` branch point so changed existing files use regression
  mode and new files still use the absolute threshold gate.

Platform note: all tests run on Linux.  The ``git show`` subprocess in
``_get_base_assessments`` is mocked; no real git repo is required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# sys.path manipulation is required before the assess import.  The skill's
# scripts directory is not on sys.path by default.
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
)
sys.path.insert(0, str(_SKILL_SCRIPTS))

# ruff: noqa: E402
from assess import (
    ChangedFile,
    FileAssessment,
    QualityScore,
    check_regressions,
    check_thresholds,
)
from assess import (
    main as assess_main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_score(value: float, confidence: float = 0.5) -> QualityScore:
    return QualityScore(value=value, confidence=confidence, reasons=[])


def _make_assessment(
    path: str = "some/file.py",
    *,
    cohesion: float = 8.0,
    coupling: float = 8.0,
    encapsulation: float = 8.0,
    testability: float = 8.0,
    non_redundancy: float = 8.0,
    confidence: float = 0.5,
) -> FileAssessment:
    return FileAssessment(
        file_path=path,
        category="production",
        cohesion=_make_score(cohesion, confidence),
        coupling=_make_score(coupling, confidence),
        encapsulation=_make_score(encapsulation, confidence),
        testability=_make_score(testability, confidence),
        non_redundancy=_make_score(non_redundancy, confidence),
    )


# ---------------------------------------------------------------------------
# check_regressions -- unit tests
# ---------------------------------------------------------------------------


class TestCheckRegressions:
    """Tests for check_regressions()."""

    def test_returns_0_when_no_regressions(self) -> None:
        """No quality dropped: returns 0."""
        head = _make_assessment(cohesion=8.0)
        base = {head.file_path: _make_assessment(cohesion=7.0)}
        assert check_regressions([head], base) == 0

    def test_returns_10_when_cohesion_drops(self) -> None:
        """Cohesion drop of 1.0 triggers exit 10."""
        head = _make_assessment(cohesion=6.0)
        base = {head.file_path: _make_assessment(cohesion=7.0)}
        assert check_regressions([head], base) == 10

    def test_returns_10_when_any_quality_drops(self) -> None:
        """Any single quality regression returns 10."""
        head = _make_assessment(testability=4.0)
        base = {head.file_path: _make_assessment(testability=6.0)}
        assert check_regressions([head], base) == 10

    def test_new_file_not_in_base_is_skipped(self) -> None:
        """A file absent from base_assessments is treated as new; not gated."""
        head = _make_assessment("new/file.py", cohesion=3.0)
        assert check_regressions([head], {}) == 0

    def test_unscored_quality_is_ignored(self) -> None:
        """Confidence 0.0 means unscored; regression check skips it."""
        head = _make_assessment(cohesion=1.0)
        head.cohesion.confidence = 0.0
        base = {head.file_path: _make_assessment(cohesion=9.0)}
        base[head.file_path].cohesion.confidence = 0.0
        assert check_regressions([head], base) == 0

    def test_drop_within_tolerance_is_not_a_regression(self) -> None:
        """Tiny floating-point drift (<=0.05) is not flagged."""
        head = _make_assessment(cohesion=7.94)
        base = {head.file_path: _make_assessment(cohesion=7.96)}
        assert check_regressions([head], base) == 0

    def test_improved_file_below_absolute_threshold_returns_0(self) -> None:
        """Core claim of issue #4364: improved but below-threshold file is OK."""
        # cohesion 5.0 < absolute threshold 7.0, but improved from 4.0 -> 5.0
        head = _make_assessment(cohesion=5.0)
        base = {head.file_path: _make_assessment(cohesion=4.0)}
        # absolute gate would return 11; regression gate must return 0
        assert check_regressions([head], base) == 0


# ---------------------------------------------------------------------------
# Verify check_thresholds still gates absolute (regression does not replace it)
# ---------------------------------------------------------------------------


class TestCheckThresholdsStillAbsolute:
    """Ensure check_thresholds still returns 11 on below-threshold files."""

    def test_returns_11_below_cohesion_threshold(self) -> None:
        config = {
            "thresholds": {
                "cohesion": {"min": 7},
                "coupling": {"min": 7},
                "encapsulation": {"min": 7},
                "testability": {"min": 6},
                "nonRedundancy": {"min": 8},
            }
        }
        assessment = _make_assessment(cohesion=5.0)
        assert check_thresholds([assessment], config, "production") == 11

    def test_returns_0_when_all_above_threshold(self) -> None:
        config = {
            "thresholds": {
                "cohesion": {"min": 7},
                "coupling": {"min": 7},
                "encapsulation": {"min": 7},
                "testability": {"min": 6},
                "nonRedundancy": {"min": 8},
            }
        }
        assessment = _make_assessment(
            cohesion=9.0,
            coupling=9.0,
            encapsulation=9.0,
            testability=9.0,
            non_redundancy=9.0,
        )
        assert check_thresholds([assessment], config, "production") == 0

    def test_regression_mode_applies_thresholds_to_new_files(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        new_file = _make_assessment("new/file.py", cohesion=5.0)
        seen: list[list[FileAssessment]] = []

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "assess.py",
                "--target",
                ".",
                "--changed-only",
                "--base",
                "origin/main",
                "--format",
                "json",
            ],
        )
        monkeypatch.setattr("assess.get_files_to_assess", lambda *_args: [Path("new/file.py")])
        monkeypatch.setattr(
            "assess.get_changed_files",
            lambda *_args, **_kwargs: [ChangedFile("A", None, Path("new/file.py"))],
        )
        monkeypatch.setattr("assess.resolve_comparison_base", lambda base: base)
        monkeypatch.setattr("assess.assess_file", lambda *_args: new_file)

        def fake_check_thresholds(
            assessments: list[FileAssessment],
            _config: dict[str, object],
            _context: str,
            **_kwargs: object,
        ) -> int:
            seen.append(assessments)
            return 11

        monkeypatch.setattr("assess.check_thresholds", fake_check_thresholds)

        assert assess_main() == 11
        assert seen == [[new_file]]

    def test_regression_mode_does_not_gate_existing_absolute_debt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        head = _make_assessment("legacy.py", cohesion=5.0)
        base = {head.file_path: _make_assessment("legacy.py", cohesion=4.0)}

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "assess.py",
                "--target",
                ".",
                "--changed-only",
                "--base",
                "origin/main",
                "--format",
                "json",
            ],
        )
        monkeypatch.setattr("assess.get_files_to_assess", lambda *_args: [Path("legacy.py")])
        monkeypatch.setattr(
            "assess.get_changed_files",
            lambda *_args, **_kwargs: [ChangedFile("M", Path("legacy.py"), Path("legacy.py"))],
        )
        monkeypatch.setattr("assess.assess_file", lambda *_args: head)
        monkeypatch.setattr("assess.get_file_at_revision", lambda *_args: b"legacy")
        monkeypatch.setattr("assess._assess_base_bytes", lambda *_args: base["legacy.py"])

        assert assess_main() == 0

    def test_regression_mode_returns_10_for_existing_score_drop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        head = _make_assessment("legacy.py", cohesion=5.0)
        base = {head.file_path: _make_assessment("legacy.py", cohesion=8.0)}

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "assess.py",
                "--target",
                ".",
                "--changed-only",
                "--base",
                "origin/main",
                "--format",
                "json",
            ],
        )
        monkeypatch.setattr("assess.get_files_to_assess", lambda *_args: [Path("legacy.py")])
        monkeypatch.setattr(
            "assess.get_changed_files",
            lambda *_args, **_kwargs: [ChangedFile("M", Path("legacy.py"), Path("legacy.py"))],
        )
        monkeypatch.setattr("assess.assess_file", lambda *_args: head)
        monkeypatch.setattr("assess.get_file_at_revision", lambda *_args: b"legacy")
        monkeypatch.setattr("assess._assess_base_bytes", lambda *_args: base["legacy.py"])

        assert assess_main() == 10


# ---------------------------------------------------------------------------
# _get_base_assessments -- mocked git show
# ---------------------------------------------------------------------------


class TestGetBaseAssessments:
    """_get_base_assessments fetches base content via git show."""

    def test_new_file_absent_from_base_is_omitted(self, tmp_path: Path) -> None:
        """Files that do not exist at the base revision are absent from result."""
        from assess import _get_base_assessments

        file_path = tmp_path / "new.py"
        file_path.write_text("x = 1\n")

        with patch(
            "assess.resolve_comparison_base",
            return_value="base",
        ), patch(
            "assess.get_file_at_revision",
            return_value=None,
        ), patch(
            "subprocess.run",
            return_value=type(
                "Result",
                (),
                {"returncode": 0, "stdout": str(tmp_path) + "\n"},
            )(),
        ):
            result = _get_base_assessments([file_path], "origin/main", "production")

        assert result == {}

    def test_existing_file_is_assessed_from_base_content(self, tmp_path: Path) -> None:
        """A file present at base is assessed from the git show content."""
        from assess import _get_base_assessments

        file_path = tmp_path / "module.py"
        file_path.write_text("def foo(): pass\n")
        base_content = "def foo(): pass\ndef bar(): pass\n"

        with patch(
            "assess.resolve_comparison_base",
            return_value="base",
        ), patch(
            "assess.get_file_at_revision",
            return_value=base_content.encode("utf-8"),
        ), patch(
            "subprocess.run",
            return_value=type(
                "Result",
                (),
                {"returncode": 0, "stdout": str(tmp_path) + "\n"},
            )(),
        ):
            result = _get_base_assessments([file_path], "origin/main", "production")

        assert str(file_path) in result
        assert result[str(file_path)].file_path == str(file_path)
