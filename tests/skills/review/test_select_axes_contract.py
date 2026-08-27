"""Axis-count, blank-path, and diff-effect contract tests for ``/review``.

Split from ``test_select_axes.py`` so both modules stay under the 500-line
taste limit. These cover the three defects the Validate Spec Coverage check
raised on PR #5361: the deep-review total, a blank-only path list that failed
open, and the issue #4981 routing rows no path glob can see.

Each block carries a negative control, so a selector stubbed to return the
full set, the empty set, or a single family fails here.
"""

from __future__ import annotations

import re
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
    module_name="review_select_axes",
)

REVIEW_SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "review"
REFERENCES_DIR = REVIEW_SKILL_DIR / "references"

# The Stage-2 candidates the shipped references/ directory yields today.
CANDIDATES = mod.discover_canonical_axes(REFERENCES_DIR)


def select(paths: list[str], **kwargs: object) -> dict:
    return mod.select_axes(changed_paths=paths, canonical_candidates=CANDIDATES, **kwargs)


class TestDeepReviewRunsTheWholeSet:
    """Issue #4981 AC-10: a full-set mode stays available for a deep review.

    The issue's Problem section counts "15 review axes" as the state BEFORE
    this work: 1 Stage-1 gate, 11 Stage-2 canonical axes, and 3 chained
    skills. Its own routing table then adds a row, "Docs and instruction
    claims -> documentation accuracy review", which enrolls ``doc-accuracy``
    as a 4th local axis, and the non-goals forbid removing an existing axis
    to compensate. So the full set is 15 Stage-2 axes and 16 reported rows.
    These assertions derive both totals rather than hardcoding them, so
    enrolling a further axis reds this test instead of silently drifting.
    """

    def test_deep_review_selects_every_canonical_and_local_axis(self) -> None:
        result = select(["docs/guide.md"], deep=True)
        assert set(result["canonical_selected"]) == set(CANDIDATES)
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)

    def test_deep_review_stage2_total_is_canonical_plus_local(self) -> None:
        result = select(["docs/guide.md"], deep=True)
        stage2 = len(result["canonical_selected"]) + len(result["local_selected"])
        assert stage2 == len(CANDIDATES) + len(mod.LOCAL_AXES)
        assert stage2 == 15, "11 canonical + 4 local with the current set"

    def test_deep_review_reports_one_more_row_than_stage2_axes(self) -> None:
        """The Stage-1 gate is a reported row but never a Stage-2 candidate."""
        result = select(["docs/guide.md"], deep=True)
        assert mod.STAGE1_AXIS not in result["canonical_selected"]
        assert mod.STAGE1_AXIS not in result["local_selected"]
        rows = 1 + len(result["canonical_selected"]) + len(result["local_selected"])
        assert rows == 16

    def test_deep_review_skips_nothing(self) -> None:
        # Negative control: a risk-mode run on the same path DOES skip axes,
        # so an assertion that passed in both modes would prove nothing.
        assert select(["docs/guide.md"], deep=True)["skipped"] == {}
        assert select(["docs/guide.md"])["skipped"] != {}


class TestBlankPathsFailClosed:
    """A path list holding nothing but blanks is not a reviewable change.

    ``classify_paths`` drops an empty-after-trimming entry instead of calling
    it unclassified, so testing the raw list let ``["   "]`` reach the risk
    branch with no category matched: ``fail_closed`` stayed false and the run
    narrowed to the always-on ``analyst`` alone.
    """

    @pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
    def test_a_list_of_only_blanks_fails_closed(self, blank: str) -> None:
        result = select([blank])
        assert result["fail_closed"] is True
        assert set(result["canonical_selected"]) == set(CANDIDATES)
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)

    def test_several_blanks_fail_closed(self) -> None:
        result = select(["", "  ", "\t"])
        assert result["fail_closed"] is True

    def test_blank_alongside_a_real_path_still_routes_by_risk(self) -> None:
        # Negative control: the fix must reject a list that is empty after
        # trimming, not any list that happens to contain a blank entry.
        result = select(["  ", "docs/guide.md"])
        assert result["fail_closed"] is False
        assert result["local_selected"] == ["doc-accuracy"]

    def test_blank_only_list_matches_the_empty_list_verdict(self) -> None:
        assert select(["   "])["fail_closed"] == select([])["fail_closed"]


class TestDiffBodyEffectsCoverTheRemainingRoutingRows:
    """Issue #4981 routing rows whose surface no path glob can see.

    "execution", "untrusted input", "artifacts", and "rollback" are diff-body
    properties. Matching them as path words over all tracked files produced
    only false positives (`eval` hit the eval-* analysis corpus, `artifacts`
    hit .agents/analysis/eval-artifacts/), so they are declared effects.
    """

    @pytest.mark.parametrize(
        ("effect", "expected"),
        [
            ("command-execution", {"security"}),
            ("untrusted-input", {"security"}),
            ("artifact-or-rollback", {"devops", "security"}),
        ],
    )
    def test_effect_selects_its_specialists(self, effect: str, expected: set[str]) -> None:
        result = select(["docs/guide.md"], effects=[effect])
        assert expected <= set(result["canonical_selected"])
        assert result["fail_closed"] is False

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/analysis/eval-artifacts/report.md",
            ".claude/commands/ship.md",
            ".agents/architecture/ADR-016-workflow-execution-optimization.md",
            ".agents/operations/pr-maintenance-rollback.md",
        ],
    )
    def test_lookalike_paths_do_not_select_security_by_name(self, path: str) -> None:
        """Negative control for the rejected path-token design.

        Each path carries an execution, artifact, or rollback WORD but is
        prose or an agent artifact, not a risk surface. Declaring the effect
        is what selects security; the filename never does.
        """
        assert mod._is_security_path(mod._norm(path)) is False

    def test_an_effect_outside_the_vocabulary_still_fails_closed(self) -> None:
        result = select(["docs/guide.md"], effects=["command-executionn"])
        assert result["fail_closed"] is True
        assert result["unknown_effects"] == ["command-executionn"]


class TestSkillCountClaimsMatchTheCode:
    """Every axis count stated in SKILL.md must equal the shipped set.

    SKILL.md carried three contradictory counts at once: "3 local axes" in
    Verification, 16 rows in Process step 7, and a Skill-chain list that
    omitted ``doc-accuracy``. Each claim is derived here, so a future axis
    enrollment reds this test rather than leaving prose behind the code.
    """

    BODY = (REVIEW_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    ROWS = 1 + len(CANDIDATES) + len(mod.LOCAL_AXES)

    def _counts(self, pattern: str) -> list[int]:
        found = [int(n) for n in re.findall(pattern, self.BODY)]
        assert found, f"SKILL.md no longer states this count: {pattern}"
        return found

    def test_every_local_axis_count_claim_matches_local_axes(self) -> None:
        claims = self._counts(r"(\d+) local(?:-only)?(?: skill)? axes")
        assert set(claims) == {len(mod.LOCAL_AXES)}, claims

    def test_every_canonical_axis_count_claim_matches_the_candidates(self) -> None:
        claims = self._counts(r"(\d+) Stage-2 canonical axes")
        assert set(claims) == {len(CANDIDATES)}, claims

    def test_every_deep_review_row_claim_matches_the_reported_rows(self) -> None:
        claims = self._counts(r"(\d+) rows") + self._counts(r"full (\d+)-axis set")
        claims += self._counts(r"(\d+) total in deep-review mode")
        assert set(claims) == {self.ROWS}, claims

    def test_the_skill_chain_names_every_local_axis(self) -> None:
        chain = next(line for line in self.BODY.splitlines() if line.startswith("- Skill chain:"))
        for axis in mod.LOCAL_AXES:
            assert axis in chain, axis
