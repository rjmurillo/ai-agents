"""The scoping note tells authors that paths outside a change heading go unchecked (#6506)."""

from __future__ import annotations

from scripts.validation.pr_description import scoping_note


def test_note_names_the_narrowing_when_a_change_heading_exists() -> None:
    body = "## Changes\nUpdated `scripts/a.py`.\n\n## Notes\nSee `scripts/b.py`."
    assert "only paths under it are checked" in scoping_note(body)


def test_no_note_without_a_change_heading() -> None:
    assert scoping_note("Updated `scripts/a.py` in passing.") == ""


def test_no_note_for_an_empty_description() -> None:
    assert scoping_note("") == ""
