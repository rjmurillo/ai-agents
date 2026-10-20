"""Guard the PR attribution in the orchestrator observations memory file."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MEMORY = (
    Path(__file__).resolve().parent.parent / ".serena" / "memories" / "orchestrator-observations.md"
)
FILE_NAME = "tests/hooks/managed_image_marker_parsers.py"


def prs_tied_to_file(text: str, file_name: str = FILE_NAME) -> set[str]:
    """Return PR numbers named before file_name within its semicolon clause."""
    tied: set[str] = set()
    for line in text.splitlines():
        if file_name not in line:
            continue
        for clause in re.split(r";", line):
            if file_name in clause:
                tied.update(re.findall(r"#(\d+)", clause.split(file_name)[0]))
    return tied


def test_fail_open_file_is_attributed_to_6681_only() -> None:
    assert prs_tied_to_file(MEMORY.read_text(encoding="utf-8")) == {"6681"}


def test_combined_attribution_ties_both_prs() -> None:
    line = f"found (#6676 and #6681, a fail-open in `{FILE_NAME}`)"
    assert prs_tied_to_file(line) == {"6676", "6681"}


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "(#6681: a fail-open in `tests/hooks/managed_image_marker_parsers.py`; #6676: other)",
            {"6681"},
        ),
        ("nothing about that file here #6676: x", set()),
        (f"(#6676 and #6681: a fail-open in `{FILE_NAME}`)", {"6676", "6681"}),
    ],
)
def test_prs_tied_to_file_splits_clauses(line: str, expected: set[str]) -> None:
    assert prs_tied_to_file(line) == expected
