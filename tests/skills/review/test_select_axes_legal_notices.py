"""Verbatim legal files no longer fail the path classifier closed (issue #7280).

A package `LICENSE` matched no risk row, so a diff that added one selected all
15 reviewer axes. Legal text carries no behavior, so it classifies under an
axis-free category. Unknown paths must still fail closed.

Kept out of ``test_select_axes.py``, which is already over the 500-line taste
limit.
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
    module_name="review_select_axes_legal_notices",
)

REFERENCES_DIR = PROJECT_ROOT / ".claude" / "skills" / "review" / "references"
CANDIDATES = tuple(mod.discover_canonical_axes(REFERENCES_DIR))

LEGAL_PATHS = [
    "LICENSE",
    "packages/ai-agents-cli/LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "NOTICE",
    "NOTICE.txt",
    "COPYING",
    "THIRD-PARTY-NOTICES",
    "src/copilot-cli/THIRD-PARTY-NOTICES.TXT",
    "vendor\\pkg\\License",
]


def select(paths: list[str], **kwargs: object) -> dict:
    return mod.select_axes(changed_paths=paths, canonical_candidates=CANDIDATES, **kwargs)


class TestLegalNoticeAlone:
    @pytest.mark.parametrize("path", LEGAL_PATHS)
    def test_does_not_fail_closed(self, path):
        result = select([path])
        assert result["fail_closed"] is False
        assert result["unclassified_paths"] == []

    @pytest.mark.parametrize("path", ["LICENSE", "NOTICE.txt", "THIRD-PARTY-NOTICES"])
    def test_selects_only_the_always_on_axes(self, path):
        result = select([path])
        assert result["canonical_selected"] == sorted(mod.ALWAYS_ON_CANONICAL)
        assert result["local_selected"] == []
        for axis in mod.ALWAYS_ON_CANONICAL:
            assert result["selection_reasons"][axis] == mod._ALWAYS_ON_REASON

    def test_reports_the_legal_notices_category(self):
        assert select(["LICENSE"])["matched_categories"] == ["legal-notices"]

    def test_pinned_axis_still_selects_beside_a_legal_file(self):
        result = select(["packages/ai-agents-cli/LICENSE"], pinned=["security"])
        assert result["fail_closed"] is False
        assert "security" in result["canonical_selected"]

    def test_deep_still_selects_every_canonical_axis(self):
        result = select(["LICENSE"], deep=True)
        assert set(result["canonical_selected"]) == set(CANDIDATES)


class TestLegalNoticeBesideOtherPaths:
    def test_license_plus_code_selects_the_code_axes_only(self):
        result = select(["packages/ai-agents-cli/LICENSE", "src/app.py"])
        assert result["fail_closed"] is False
        assert result["unclassified_paths"] == []
        assert result["matched_categories"] == ["legal-notices", "executable-code"]
        assert "code-quality" in result["canonical_selected"]
        assert set(result["canonical_selected"]) < set(CANDIDATES)

    def test_license_adds_no_axis_to_the_code_selection(self):
        with_license = select(["LICENSE", "src/app.py"])
        without = select(["src/app.py"])
        assert with_license["canonical_selected"] == without["canonical_selected"]
        assert with_license["local_selected"] == without["local_selected"]


class TestUnknownPathsStillFailClosed:
    @pytest.mark.parametrize(
        "path",
        [
            "some/unclassifiable/blob.bin",
            "LICENSE-extra.bin",
            "licenses/MIT",
            "LICENSE.py.bak",
            "NOTICES.dat",
            "CHANGELOG.txt",
        ],
    )
    def test_unknown_path_alone_fails_closed(self, path):
        result = select([path])
        assert result["fail_closed"] is True
        assert result["unclassified_paths"] == [path]
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_unknown_path_beside_a_license_still_fails_closed(self):
        """Negative control: a classified LICENSE must not launder its neighbor."""
        result = select(["LICENSE", "some/unclassifiable/blob.bin"])
        assert result["fail_closed"] is True
        assert result["unclassified_paths"] == ["some/unclassifiable/blob.bin"]
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_empty_path_list_still_fails_closed(self):
        assert select([])["fail_closed"] is True


class TestUnreviewablePaths:
    @pytest.mark.parametrize("path", LEGAL_PATHS)
    def test_legal_file_is_not_stranded(self, path):
        """The axis-free row is reviewed by the always-on analyst, not by nobody."""
        assert mod.unreviewable_paths([path]) == []

    def test_unrouted_text_is_still_stranded_or_unclassified(self):
        categories, unclassified = mod.classify_paths(["notes.txt"])
        assert categories == []
        assert unclassified == ["notes.txt"]
