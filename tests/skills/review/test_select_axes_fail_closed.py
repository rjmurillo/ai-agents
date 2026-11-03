"""Fail-closed runs narrow local axes to what each scanner reads (issue #7031).

A fail-closed run once kept all four local axes. When it failed closed on an
unclassified path, golden-principles scanned zero files and reported UNKNOWN.
The marker validator rejects UNKNOWN, so no fix round could clear the row. The
path list stays trustworthy on a fail-closed run, so a scanner that reads no
changed file is skipped with a reason. Only a run with no usable path keeps all
four, because there is nothing to narrow against.

Kept out of ``test_select_axes.py``, which is already over the 500-line taste
limit, and ``test_select_axes_scanner_capability.py``, which is near it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/select_axes.py",
    module_name="review_select_axes_fail_closed",
)

REFERENCES_DIR = PROJECT_ROOT / ".claude" / "skills" / "review" / "references"
CANDIDATES = tuple(mod.discover_canonical_axes(REFERENCES_DIR))


def select(paths: list[str], **kwargs: object) -> dict:
    return mod.select_axes(changed_paths=paths, canonical_candidates=CANDIDATES, **kwargs)


class TestFailClosedNarrowsLocalAxes:
    @pytest.mark.parametrize(
        "unclassified",
        # The two #6506 branches that hit the deadlock on 2026-11-01.
        ["src/cursor/rules/python.mdc", ".agents/governance/agent-source-divergence.json"],
    )
    def test_fail_closed_skips_golden_principles_with_no_applicable_file(self, unclassified):
        """Issue #7031: GP scanned zero files, reported UNKNOWN, and blocked PASS."""
        result = select([unclassified])
        assert result["fail_closed"] is True
        assert "golden-principles" not in result["local_selected"]
        assert result["skipped"]["golden-principles"] == mod._UNREADABLE_REASON
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_fail_closed_keeps_a_scanner_that_reads_one_changed_file(self):
        """Negative control: narrowing must not drop a scanner with work to do."""
        result = select(["some/unclassifiable/blob.bin", "src/app.py", "README.md"])
        assert result["fail_closed"] is True
        assert {"code-qualities-assessment", "taste-lints", "doc-accuracy"} <= set(
            result["local_selected"]
        )
        for axis in result["local_selected"]:
            assert result["selection_reasons"][axis] == mod._FAIL_CLOSED_REASON

    @pytest.mark.parametrize("stranded", ["README.MD", ".doc-accuracy/notes.md"])
    def test_stranded_doc_skips_doc_accuracy_and_keeps_every_canonical_axis(self, stranded):
        """unreviewable_paths folds these in; the canonical axes now review them.

        doc-accuracy cannot read either path, so keeping it would scan zero
        files into an UNKNOWN that blocks PASS on every round.
        """
        result = select([stranded])
        assert result["fail_closed"] is True
        assert result["unclassified_paths"] == [stranded]
        assert result["skipped"]["doc-accuracy"] == mod._UNREADABLE_REASON
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_fail_closed_with_blank_only_paths_keeps_every_local_axis(self):
        """With nothing to narrow against, all four local axes still run.

        The empty-list case lives in test_select_axes.py.
        """
        result = select(["", "   "])
        assert result["fail_closed"] is True
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)
        assert result["skipped"] == {}

    def test_fail_closed_pin_overrides_the_scanner_narrowing(self):
        result = select(["some/unclassifiable/blob.bin"], pinned=["golden-principles"])
        assert "golden-principles" in result["local_selected"]
        assert "golden-principles" not in result["skipped"]
