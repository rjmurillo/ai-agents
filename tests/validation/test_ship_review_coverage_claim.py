"""The /ship template must claim only the coverage a review marker declares."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHIP_TEMPLATE = REPO_ROOT / "templates" / "skills" / "ship.SKILL.md.tmpl"
UNCONDITIONAL = "a passing marker covers golden-principles, taste-lints, and code-quality"


def _text() -> str:
    return SHIP_TEMPLATE.read_text(encoding="utf-8")


def test_ship_makes_no_unconditional_standards_claim() -> None:
    assert UNCONDITIONAL not in _text()
    assert "already runs the same canonical axes" not in _text()


def test_ship_reports_declared_axes_and_keeps_skipped_distinct() -> None:
    text = _text()
    assert "Coverage is what the marker declares" in text
    assert "`NOT RUN`, not passed" in text


def test_ship_names_the_required_axis_mechanism() -> None:
    assert "--require-axis" in _text()
