"""Regression test for Issue #2192: dash prohibition in tests/evals/.

Two U+2014 (em-dash) characters slipped into
``tests/evals/test_eval_agent_vs_baseline.py`` (lines 1312, 2535 on
the offending revision) because the dash-prohibition guards
(``scripts/validation/pre_pr.py::validate_dash_prohibition`` and the
markdown-only loop in ``.githooks/pre-commit``) scan only ``*.md``
files, not Python sources.

This test gives the affected file a Python-side regression check so
future edits cannot reintroduce U+2014 / U+2013 here without a
failing test. The check is intentionally narrow: expanding the guard
to every ``.py`` file in the repo is a separate, larger change
tracked elsewhere; this test pins down the specific file the issue
called out and the directory it lives under.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Pattern uses Python escapes so this source file itself stays clean
# of the prohibited characters (same convention used by
# tests/hooks/test_dash_guard.py).
_DASH_PATTERN = re.compile(r"[\u2013\u2014]")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EVAL_TEST = _REPO_ROOT / "tests" / "evals" / "test_eval_agent_vs_baseline.py"


def test_eval_agent_vs_baseline_has_no_unicode_dashes() -> None:
    """Issue #2192: file must not contain U+2014 / U+2013."""
    assert _EVAL_TEST.is_file(), f"target file missing: {_EVAL_TEST}"
    text = _EVAL_TEST.read_text(encoding="utf-8")
    hits = [
        (lineno, line)
        for lineno, line in enumerate(text.splitlines(), start=1)
        if _DASH_PATTERN.search(line)
    ]
    assert not hits, (
        "Unicode dashes (U+2014 / U+2013) found in "
        f"{_EVAL_TEST.relative_to(_REPO_ROOT)} "
        "(Issue #2192). Replace U+2014 with comma/period/colon; "
        "U+2013 with hyphen. Offending lines: "
        + ", ".join(str(lineno) for lineno, _ in hits)
    )


def test_dash_pattern_matches_both_dashes() -> None:
    """Negative-control: regex actually fires on the prohibited chars."""
    assert _DASH_PATTERN.search("\u2014")
    assert _DASH_PATTERN.search("\u2013")
    assert not _DASH_PATTERN.search("plain ASCII - hyphen only")


@pytest.mark.parametrize(
    "ok_char",
    ["-", ":", ",", ".", "(", ")", "/"],
)
def test_ascii_punctuation_is_allowed(ok_char: str) -> None:
    """Negative tests: ordinary ASCII punctuation must NOT match."""
    assert not _DASH_PATTERN.search(ok_char)
