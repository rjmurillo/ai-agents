"""Em/en-dash prohibition guard tests (Issue #1923, REQ-006).

Test skeleton populated by M2 (TASK-006-2). Assertions for the pre-commit
section (M3a, TASK-006-3) and the commit-msg hook (M3b, TASK-006-4) land
in those milestones. This module currently verifies fixture integrity so
later milestones can rely on the fixture invariants.

Fixtures live under ``tests/hooks/fixtures/``. Each fixture is generated
programmatically with Python escape sequences (see M2 implementation) so
the source files of this repo do not themselves carry the prohibited
characters. The encoded UTF-8 bytes land in the fixture files only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# REPO_ROOT is the ai-agents checkout root. tests/hooks/test_dash_guard.py is
# three levels deep (tests/hooks/test_dash_guard.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "hooks" / "fixtures"

# Compiled detection regex. The pattern itself uses Python escape sequences
# so this source file stays clean of the prohibited characters.
DASH_PATTERN = re.compile(r"[\u2013\u2014]")


@pytest.fixture(scope="module")
def fixture_dir() -> Path:
    """Locate the fixtures directory and assert it exists."""
    assert FIXTURES.is_dir(), f"Fixture directory missing: {FIXTURES}"
    return FIXTURES


def test_dash_violations_fixture_contains_both_dashes(fixture_dir: Path) -> None:
    """REQ-006-AC9 fixture invariant: dash_violations.md has U+2014 and U+2013."""
    text = (fixture_dir / "dash_violations.md").read_text(encoding="utf-8")
    assert "\u2014" in text, "fixture should contain U+2014 (em-dash)"
    assert "\u2013" in text, "fixture should contain U+2013 (en-dash)"


def test_no_dash_clean_fixture_has_neither_dash(fixture_dir: Path) -> None:
    """REQ-006-AC10 fixture invariant: no_dash_clean.md has neither dash."""
    text = (fixture_dir / "no_dash_clean.md").read_text(encoding="utf-8")
    assert not DASH_PATTERN.search(text), "clean fixture must not contain dashes"


def test_instructions_tree_fixture_has_em_dash(fixture_dir: Path) -> None:
    """REQ-006-AC4 + REQ-006-AC11 fixture invariant: mirror-tree fixture has U+2014."""
    text = (fixture_dir / "instructions_tree" / "dash_violations.md").read_text(
        encoding="utf-8",
    )
    assert "\u2014" in text, (
        "instructions-tree fixture should contain U+2014 to verify the guard"
        " applies identically to the .github/instructions/ tree (REQ-006-AC4)"
    )


def test_node_modules_fixture_has_em_dash(fixture_dir: Path) -> None:
    """REQ-006-AC5 fixture invariant: vendored fixture has U+2014.

    The fixture must contain a dash so we can prove the guard *skips*
    vendored paths; if the fixture were clean, the skip behavior would be
    indistinguishable from absence-of-violation.
    """
    text = (fixture_dir / "node_modules" / "dash_violations.md").read_text(
        encoding="utf-8",
    )
    assert "\u2014" in text, "vendored fixture should contain U+2014"


# M3 (hook integration) and M4 (pre_pr.py validate_dash_prohibition) tests
# extend this module. They import the production helpers and exercise the
# detection logic with the same fixtures, so fixture invariants above act
# as preconditions for those tests.
