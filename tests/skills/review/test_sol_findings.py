"""Tests for the pure finding rules of the cross-family Sol pass.

A kept finding needs a file, a line, and a repro, and is never a style nit.
Overlap with the critic decides ``sol_only``. Failure messages map to classes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

rules = import_skill_script(
    ".claude/skills/review/scripts/sol_findings.py", module_name="sol_findings_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)


def _finding(**overrides):
    base = {
        "file": "src/app/b.py",
        "line": 5,
        "repro": "pytest tests/test_b.py::test_empty fails with KeyError",
        "summary": "KeyError on empty input",
        "severity": "high",
        "category": "correctness",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"file": ""}, "missing-file"),
        ({"file": None}, "missing-file"),
        ({"line": None}, "missing-line"),
        ({"line": 0}, "missing-line"),
        ({"line": "12"}, "missing-line"),
        ({"line": True}, "missing-line"),
        ({"repro": ""}, "missing-repro"),
        ({"repro": "   "}, "missing-repro"),
        ({"category": "Style"}, "style-nit"),
        ({"category": "style-nit"}, "style-nit"),
        ({"category": "naming"}, "style-nit"),
        ({"category": "Cosmetic"}, "style-nit"),
        ({"category": "readability"}, "style-nit"),
        ({"category": "formatting"}, "style-nit"),
    ],
)
def test_drops_incomplete_or_style_findings(override, reason):
    kept, dropped = rules.filter_findings([_finding(**override)])

    assert kept == []
    assert dropped[0]["reason"] == reason


def test_drops_non_object_findings():
    kept, dropped = rules.filter_findings(["src/a.py:1 bad"])

    assert kept == []
    assert dropped[0]["reason"] == "not-an-object"


@pytest.mark.parametrize("category", ["correctness", "security", "data-loss", ""])
def test_keeps_complete_defect_finding(category):
    kept, dropped = rules.filter_findings([_finding(category=category)])

    assert dropped == []
    assert kept[0]["file"] == "src/app/b.py"


@pytest.mark.parametrize(
    ("critic", "file", "line", "sol_only"),
    [
        ("src/app/a.py:10", "src/app/a.py", 13, False),
        ("src/app/a.py:10", "src/app/a.py", 14, True),
        ("foo.py:10-40", "foo.py", 30, False),
        ("foo.py:10-40", "foo.py", 44, True),
        ("see app/a.py:10", "a.py", 10, False),
        ("./src/x.py:5", "src/x.py", 5, False),
        (".claude/x.py:5", "claude/x.py", 5, True),
        ("src/other.py:10", "src/app/a.py", 10, True),
    ],
)
def test_overlap_rule(critic, file, line, sol_only):
    marked = rules.mark_sol_only([_finding(file=file, line=line)], critic)

    assert marked[0]["sol_only"] is sol_only


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("The 'x' model is not supported when using Codex", "model-unsupported"),
        ("rate limit exceeded", "rate-limit"),
        ("HTTP 429 Too Many Requests", "rate-limit"),
        ("request id 4290ab: connection reset", "unknown"),
        ("You hit your usage limit", "quota"),
        ("401 Unauthorized: not logged in", "auth"),
        ("HTTP 503 service unavailable", "5xx"),
        ("upstream connect error", "unknown"),
    ],
)
def test_failure_classification(message, expected):
    assert rules.classify_failure(message) == expected


def test_failure_message_reads_turn_failed_event():
    events = '{"type":"thread.started"}\n{"type":"turn.failed","error":{"message":"model gone"}}\n'

    assert rules.failure_message(events, "stderr noise") == "model gone"
