"""Check that the shipped skill carries the friction report format and its noise guard."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

_FORMAT_LINES = ("Hit: <", "Did instead: <", "Permanent fix: <")


def _section() -> str:
    text = (_ROOT / "src/claude/skills/avoiding-manufactured-work/SKILL.md").read_text(
        encoding="utf-8"
    )
    return text.split("## Friction Report", 1)[1].split("\n## ", 1)[0]


def test_shipped_skill_carries_the_report_format() -> None:
    section = _section()
    for prefix in _FORMAT_LINES:
        assert prefix in section


def test_shipped_skill_reports_without_reopening() -> None:
    section = _section()
    assert "does not reopen the task or authorize a fix" in section
    assert "Skip style preferences and steps that ran as intended" in section
