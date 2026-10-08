"""Tests for per-file threshold context in assess.py (issue #6166).

Without ``--context``, each file is gated on the thresholds of its own
category: authored files use production, test files use ``context.test``,
generated files use ``context.generated``. An explicit ``--context`` still
overrides the category for every file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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
    check_regression,
    check_thresholds,
)
from assess import (
    main as assess_main,
)

_CONFIG = {
    "thresholds": {
        "cohesion": {"min": 7},
        "coupling": {"min": 7},
        "encapsulation": {"min": 7},
        "testability": {"min": 6},
        "nonRedundancy": {"min": 8},
    },
    "context": {
        "test": {"testability": {"min": 3}},
        "generated": {"testability": {"min": 1}},
    },
}

# Testability 4 passes the test threshold (3) and fails production (6).
_TESTABILITY = 4.0


def _score(value: float) -> QualityScore:
    return QualityScore(value=value, confidence=0.5, reasons=[])


def _assessment(path: str, category: str) -> FileAssessment:
    return FileAssessment(
        file_path=path,
        category=category,
        cohesion=_score(8.0),
        coupling=_score(8.0),
        encapsulation=_score(8.0),
        testability=_score(_TESTABILITY),
        non_redundancy=_score(8.0),
    )


class TestAbsoluteMode:
    def test_test_file_uses_test_thresholds_without_context(self) -> None:
        a = _assessment("tests/test_new.py", "test")
        assert check_thresholds([a], _CONFIG, None) == 0

    def test_authored_file_keeps_production_thresholds(self) -> None:
        a = _assessment("src/mod.py", "authored")
        assert check_thresholds([a], _CONFIG, None) == 11

    def test_generated_file_uses_generated_thresholds(self) -> None:
        a = _assessment("gen/out.py", "generated")
        assert check_thresholds([a], _CONFIG, None) == 0

    def test_explicit_production_overrides_test_category(self) -> None:
        a = _assessment("tests/test_new.py", "test")
        assert check_thresholds([a], _CONFIG, "production") == 11

    def test_explicit_test_overrides_authored_category(self) -> None:
        a = _assessment("src/mod.py", "authored")
        assert check_thresholds([a], _CONFIG, "test") == 0

    def test_mixed_batch_fails_only_on_the_authored_file(self) -> None:
        batch = [
            _assessment("tests/test_new.py", "test"),
            _assessment("src/mod.py", "authored"),
        ]
        assert check_thresholds(batch, _CONFIG, None) == 11

    def test_unknown_category_falls_back_to_production(self) -> None:
        a = _assessment("x.py", "mystery")
        assert check_thresholds([a], _CONFIG, None) == 11

    def test_missing_context_config_uses_base_thresholds(self) -> None:
        a = _assessment("tests/test_new.py", "test")
        cfg = {"thresholds": _CONFIG["thresholds"]}
        assert check_thresholds([a], cfg, None) == 11


class TestRegressionModeNewFiles:
    def test_new_test_file_uses_test_thresholds_without_context(self) -> None:
        a = _assessment("tests/test_new.py", "test")
        assert check_regression([], [a], _CONFIG, None) == 0

    def test_new_authored_file_keeps_production_thresholds(self) -> None:
        a = _assessment("src/mod.py", "authored")
        assert check_regression([], [a], _CONFIG, None) == 11

    def test_explicit_production_overrides_new_test_file(self) -> None:
        a = _assessment("tests/test_new.py", "test")
        assert check_regression([], [a], _CONFIG, "production") == 11


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    assessment: FileAssessment,
    *extra: str,
    regression: bool,
) -> int:
    cfg = tmp_path / "qualityrc.json"
    cfg.write_text(json.dumps(_CONFIG), encoding="utf-8")
    path = Path(assessment.file_path)
    argv = ["--target", ".", "--format", "json", "--config", str(cfg), *extra]
    if regression:
        argv += ["--changed-only", "--base", "origin/main"]
        monkeypatch.setattr(
            "assess.get_changed_files",
            lambda *_a, **_k: [ChangedFile("A", None, path)],
        )
        monkeypatch.setattr("assess.resolve_comparison_base", lambda base: base)
    monkeypatch.setattr("assess.get_files_to_assess", lambda *_a: [path])
    monkeypatch.setattr("assess.assess_file", lambda *_a: assessment)
    return assess_main(argv)


class TestCli:
    @pytest.mark.parametrize("regression", [False, True])
    def test_new_test_file_passes_without_context_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = _assessment("tests/test_new.py", "test")
        assert _run_main(monkeypatch, tmp_path, a, regression=regression) == 0

    @pytest.mark.parametrize("regression", [False, True])
    def test_explicit_production_still_fails_test_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = _assessment("tests/test_new.py", "test")
        rc = _run_main(monkeypatch, tmp_path, a, "--context", "production", regression=regression)
        assert rc == 11

    @pytest.mark.parametrize("regression", [False, True])
    def test_authored_file_fails_without_context_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = _assessment("src/mod.py", "authored")
        assert _run_main(monkeypatch, tmp_path, a, regression=regression) == 11

    @pytest.mark.parametrize("bad", ["prod", "Test", ""])
    def test_invalid_context_is_rejected(self, bad: str) -> None:
        with pytest.raises(SystemExit):
            assess_main(["--target", ".", "--context", bad])
