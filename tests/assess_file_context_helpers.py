"""Shared fixtures for the per-file threshold context tests (issue #6166)."""

from __future__ import annotations

import sys
from pathlib import Path

_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

# ruff: noqa: E402
from assess import (
    ChangedFile,
    FileAssessment,
    QualityScore,
    check_regression,
    check_thresholds,
    generate_markdown_report,
)
from assess import main as assess_main

__all__ = [
    "CONFIG",
    "TESTABILITY",
    "ChangedFile",
    "FileAssessment",
    "assess_main",
    "assessment",
    "check_regression",
    "check_thresholds",
    "generate_markdown_report",
]

CONFIG = {
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
TESTABILITY = 4.0


def _score(value: float) -> QualityScore:
    return QualityScore(value=value, confidence=0.5, reasons=[])


def assessment(path: str, category: str) -> FileAssessment:
    return FileAssessment(
        file_path=path,
        category=category,
        cohesion=_score(8.0),
        coupling=_score(8.0),
        encapsulation=_score(8.0),
        testability=_score(TESTABILITY),
        non_redundancy=_score(8.0),
    )
