"""The eval README lists every entry-point script (review finding 9).

An entry point is an `actionability_*.py` or `measure_actionability_band.py` file with a
`__main__` guard. Each needs a row in the Scripts table of `scripts/eval/README.md` that
points at the runbook, `evals/comment-actionability/README.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _ROOT / "scripts" / "eval"
_README = _EVAL_DIR / "README.md"
_RUNBOOK = "evals/comment-actionability/README.md"


def _entry_points() -> list[str]:
    candidates = [
        *_EVAL_DIR.glob("actionability_*.py"),
        _EVAL_DIR / "measure_actionability_band.py",
    ]
    return sorted(
        p.name for p in candidates if 'if __name__ == "__main__":' in p.read_text(encoding="utf-8")
    )


def _table_rows() -> dict[str, str]:
    """Map script name to its table row text, for rows of the form `| `name` | ...`."""
    rows: dict[str, str] = {}
    for line in _README.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `([^`]+\.py)` \|", line)
        if match:
            rows[match.group(1)] = line
    return rows


class TestScriptsTable:
    def test_the_entry_points_are_the_three_expected_scripts(self) -> None:
        """Premise: the discovery rule finds the corpus, arms, and band scripts."""
        assert _entry_points() == [
            "actionability_arms.py",
            "actionability_corpus.py",
            "measure_actionability_band.py",
        ]

    @pytest.mark.parametrize("script", _entry_points())
    def test_each_entry_point_has_a_row_pointing_at_the_runbook(self, script: str) -> None:
        """A script with no row, or a row with no runbook link, fails here."""
        rows = _table_rows()

        assert script in rows, f"{script} is missing from the Scripts table"
        assert _RUNBOOK in rows[script]

    def test_the_runbook_exists(self) -> None:
        """The pointer must not dangle."""
        assert (_ROOT / _RUNBOOK).is_file()

    def test_library_modules_are_not_listed_as_entry_points(self) -> None:
        """Only scripts people run get a row. Shared modules stay out of the table."""
        rows = _table_rows()

        for library in ("actionability_io.py", "actionability_labels.py", "actionability_scan.py"):
            assert library not in rows
