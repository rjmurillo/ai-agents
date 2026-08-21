"""Duplicate-key detection in detect_adr_changes, across both shipped trees.

Split out of ``test_detect_adr_changes.py`` to keep that module under the
500-line ceiling, the same reason ``test_detect_adr_changes_encoding.py`` was
split out earlier in this campaign.

The subject is one contract: a repeated frontmatter key must fail the
exemption closed, whatever spelling YAML accepts for it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "skills"))

from claude_skills_import import import_skill_script

_DETECTOR_TREES = [
    ".claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py",
]


class TestDuplicateKeySpellings:
    """Quoting must not launder a duplicate past the exemption guard.

    `_has_duplicate_top_level_keys` matched `^[A-Za-z0-9_-]+:` line prefixes,
    which asks a different question than YAML does. Measured on that revision,
    three of these four spellings walked through while `yaml.safe_load` resolved
    every one of them to `accepted`, so a record could declare `proposed` in the
    line a human reads and have `accepted` enforced. Copilot found it on
    PR #5230.

    Parametrized over both shipped trees: the Copilot copy is a mirror, and a
    guard fixed in one tree and not the other is a guard the plugin's consumers
    do not have.
    """

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    @pytest.mark.parametrize(
        "first_line",
        [
            "status: proposed",
            '"status": proposed',
            "'status': proposed",
            "status : proposed",
        ],
    )
    def test_every_spelling_is_caught(self, tree: str, first_line: str) -> None:
        detector = import_skill_script(tree)
        frontmatter = f"id: A\n{first_line}\nstatus: accepted\n"

        assert detector._has_duplicate_top_level_keys(frontmatter) is True

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    def test_a_nested_duplicate_is_caught(self, tree: str) -> None:
        """A line scan structurally cannot reach this; the parser can."""
        detector = import_skill_script(tree)

        assert detector._has_duplicate_top_level_keys("id: A\nmeta:\n  n: 1\n  n: 2\n") is True

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    def test_clean_frontmatter_is_not_flagged(self, tree: str) -> None:
        """Negative control.

        Without this, a detector that returned True unconditionally would pass
        every case above and be indistinguishable from a correct one.
        """
        detector = import_skill_script(tree)

        assert detector._has_duplicate_top_level_keys("id: A\nstatus: accepted\n") is False

    @pytest.mark.parametrize("tree", _DETECTOR_TREES)
    def test_a_distinct_nested_mapping_is_not_flagged(self, tree: str) -> None:
        """Second negative control: nesting alone is not duplication."""
        detector = import_skill_script(tree)

        assert detector._has_duplicate_top_level_keys("id: A\nmeta:\n  n: 1\n  other: 2\n") is False
