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
    Each total is asserted twice: once derived from the shipped set, and once
    pinned to today's number. The derived half holds the contract, the pinned
    half is the tripwire, so enrolling a further axis reds this test instead of
    drifting silently.
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


class TestAgentArtifactMatchingIsSegmentShaped:
    """The agent-artifact tokens over-fired and under-fired at the same time.

    ``_AGENT_ARTIFACT_TOKENS`` matched bare substrings, so ``skill.md`` inside
    ``req-019-autoplan-router-skill.md`` selected ``agent-safety`` and
    ``golden-principles`` on a requirements document, while ``/skills/`` with
    its leading slash could not match a repo-root ``skills/`` directory at all.
    The second half is the worse one: an agent artifact in the vendored plugin
    layout SKILL.md documents skipped ``agent-safety`` silently, which fails
    open against this module's fail-closed rule.
    """

    # Real tracked files. Each is prose whose name merely ends "-skill.md".
    OVER_FIRE = [
        ".agents/specs/requirements/req-019-autoplan-router-skill.md",
        ".serena/memories/testing/testing-get-pr-checks-skill.md",
        ".agents/archive/planning/eval-617-spec-generator-skill.md",
    ]

    # The repo-root layout a vendored plugin install presents (SKILL.md
    # "Path resolution", candidate 3), which the leading-slash tokens missed.
    UNDER_FIRE = [
        "skills/review/SKILL.md",
        "agents/planner.md",
        "hooks/session_start.py",
        "prompts/security.md",
        "commands/ship.md",
    ]

    # Positive control: the shapes that already worked must keep working.
    STILL_MATCH = [
        ".claude/skills/review/SKILL.md",
        "src/copilot-cli/skills/review/scripts/select_axes.py",
        ".claude/agents/implementer.md",
        ".agents/hooks/hooks.yaml",
    ]

    @pytest.mark.parametrize("path", OVER_FIRE)
    def test_prose_named_like_a_skill_selects_no_agent_axis(self, path: str) -> None:
        result = select([path])
        assert "agent-safety" not in result["canonical_selected"], path
        assert "golden-principles" not in result["local_selected"], path
        # Guard the guard: an unclassified path would fail closed and select
        # everything, which would pass the two assertions above for the wrong
        # reason. These paths classify as docs, so risk mode really ran.
        assert result["fail_closed"] is False, path

    @pytest.mark.parametrize("path", UNDER_FIRE)
    def test_repo_root_artifact_directories_select_agent_safety(self, path: str) -> None:
        result = select([path])
        assert "agent-safety" in result["canonical_selected"], result["matched_categories"]

    @pytest.mark.parametrize("path", STILL_MATCH)
    def test_nested_artifact_paths_still_select_agent_safety(self, path: str) -> None:
        result = select([path])
        assert "agent-safety" in result["canonical_selected"], result["matched_categories"]

    def test_root_rules_directory_selects_golden_principles(self) -> None:
        assert "golden-principles" in select(["rules/universal.md"])["local_selected"]

    def test_workflow_still_selects_golden_principles(self) -> None:
        # Negative control for the rewrite: toolkit-governance must not have
        # collapsed into agent-artifacts and lost its CI half.
        result = select([".github/workflows/ci.yml"])
        assert "golden-principles" in result["local_selected"]
        assert "agent-safety" not in result["canonical_selected"]

    @pytest.mark.parametrize("path", ["docs/skills", "src/agents", "notes/hooks"])
    def test_a_file_named_like_an_artifact_directory_is_not_one(self, path: str) -> None:
        """Edge: the last segment is the filename, never a directory."""
        assert mod._is_agent_artifact_path(mod._norm(path)) is False, path

    @pytest.mark.parametrize(
        "path",
        [".claude\\skills\\review\\SKILL.md", ".CLAUDE/SKILLS/REVIEW/SKILL.MD"],
    )
    def test_separator_and_case_variants_still_match(self, path: str) -> None:
        """Edge: normalization runs before segment matching, in both layouts."""
        assert mod._is_agent_artifact_path(mod._norm(path)) is True, path

    def test_an_ordinary_source_path_matches_neither_category(self) -> None:
        assert mod._is_agent_artifact_path("src/service.py") is False
        assert mod._is_toolkit_artifact_path("src/service.py") is False


class TestPathPredicatesMatchSegmentsNotSubstrings:
    """Three predicates read raw substrings and dropped a required axis.

    Each failure is silent, which is what makes it worse than an over-fire:
    the path still classifies as something (executable-code, or
    docs-and-instructions), so ``fail_closed`` stays false, no unclassified
    path is reported, and the missing specialist looks like a deliberate skip.

    * ``Button.test.tsx`` and ``router.spec.js`` matched no (name, extension)
      pair, so a real test file skipped ``qa``.
    * ``fixtures/sample.json`` at the repository root matched neither
      ``/fixtures/`` nor any suffix, so it classified as nothing and paid for
      a full fail-closed review.
    * ``src/prototypes.py`` contains ``types.py`` and selected ``architect``;
      ``src/types.go`` matched nothing and skipped it.
    * ``roadmap/plan.md`` and ``decisions/record.md`` missed their leading
      slash, so ``roadmap`` and ``decision-rigor`` never ran.

    Every positive case asserts ``fail_closed is False`` as well, because a
    fail-closed run selects every axis and would satisfy the axis assertion
    for the wrong reason.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "src/Button.test.tsx",
            "web/router.spec.js",
            "app/Cache.Tests.ps1",
            "pkg/handler_test.go",
            "lib/parser_spec.rb",
        ],
    )
    def test_an_extension_neutral_test_name_selects_qa(self, path: str) -> None:
        result = select([path])
        assert "qa" in result["canonical_selected"], result["matched_categories"]
        assert result["fail_closed"] is False, path

    def test_a_repo_root_fixtures_directory_is_test_adjacent(self) -> None:
        result = select(["fixtures/sample.json"])
        assert result["unclassified_paths"] == []
        assert result["fail_closed"] is False
        assert "qa" in result["canonical_selected"]

    @pytest.mark.parametrize(
        "path", ["src/service.py", "docs/guide.md", "src/latest.py", "docs/fixtures"]
    )
    def test_an_ordinary_path_is_still_not_a_test(self, path: str) -> None:
        """Negative control, including a FILE named ``fixtures``."""
        assert mod._is_test_path(mod._norm(path)) is False, path

    @pytest.mark.parametrize(
        "path",
        [
            "src/types.go",
            "src/types.ts",
            "app/api.rs",
            "pkg/models.cs",
            "core/protocols.py",
            "proto/user.proto",
            "web/global.d.ts",
            "schemas/user.json",
            "interfaces/reader.ts",
        ],
    )
    def test_a_whole_type_or_api_name_selects_architect(self, path: str) -> None:
        result = select([path])
        assert "architect" in result["canonical_selected"], result["matched_categories"]
        assert result["fail_closed"] is False, path

    @pytest.mark.parametrize("path", ["src/prototypes.py", "src/subtypes.ts", "lib/apiary.py"])
    def test_a_name_that_merely_contains_a_type_token_does_not(self, path: str) -> None:
        result = select([path])
        assert mod._is_type_or_api_path(mod._norm(path)) is False, path
        assert "architect" not in result["canonical_selected"], path
        assert result["fail_closed"] is False, path

    @pytest.mark.parametrize(
        ("path", "axis"),
        [
            ("roadmap/plan.md", "roadmap"),
            ("planning/work.md", "roadmap"),
            ("specs/req-001.md", "roadmap"),
            ("decisions/record.md", "decision-rigor"),
            ("architecture/overview.md", "decision-rigor"),
        ],
    )
    def test_a_repo_root_doc_directory_selects_its_specialist(
        self, path: str, axis: str
    ) -> None:
        result = select([path])
        assert axis in result["canonical_selected"], result["matched_categories"]
        assert result["fail_closed"] is False, path

    def test_root_and_nested_layouts_route_alike(self) -> None:
        assert (
            select(["roadmap/plan.md"])["canonical_selected"]
            == select([".agents/roadmap/plan.md"])["canonical_selected"]
        )

    @pytest.mark.parametrize("path", ["docs/roadmapping.md", "docs/decisiveness.md"])
    def test_a_directory_name_prefix_is_not_a_directory(self, path: str) -> None:
        """Negative control: segment matching must not become a prefix match."""
        assert mod._is_roadmap_doc_path(mod._norm(path)) is False, path
        assert mod._is_decision_doc_path(mod._norm(path)) is False, path

    def test_conftest_py_is_test_adjacent(self) -> None:
        """AI-Spec-Validation on PR #5361: pytest loads conftest.py by exact
        name, not by a test_/_test spelling, so the old prefix/infix check
        silently skipped qa on it. Placed outside any tests/fixtures
        directory so the existing directory check cannot pass this by
        accident."""
        result = select(["src/conftest.py"])
        assert "qa" in result["canonical_selected"], result["matched_categories"]
        assert result["fail_closed"] is False

    @pytest.mark.parametrize("path", ["src/conftest_helpers.py", "src/myconftest.py"])
    def test_a_name_that_merely_contains_conftest_is_not_conftest(self, path: str) -> None:
        """Negative control: exact-filename matching must not become a substring match."""
        assert mod._is_test_path(mod._norm(path)) is False, path

    @pytest.mark.parametrize(
        "path",
        [
            "src/authentication/session.py",
            "src/authorization/policy.py",
            "src/security/policy.py",
        ],
    )
    def test_an_authn_authz_security_directory_selects_security(self, path: str) -> None:
        """AI-Spec-Validation on PR #5361: these directories classified as
        executable code only, so fail_closed stayed False and the security
        axis was silently skipped."""
        result = select([path])
        assert "security" in result["canonical_selected"], result["matched_categories"]
        assert result["fail_closed"] is False, path

    @pytest.mark.parametrize("path", ["docs/authenticity.md", "src/authors.py"])
    def test_a_word_that_merely_contains_auth_is_not_security(self, path: str) -> None:
        """Negative control: whole-word matching must not become a substring match."""
        assert mod._is_security_path(mod._norm(path)) is False, path


class TestConvergenceContractDoesNotPromiseZeroEditEnrollment:
    """The contract claimed enrolling an axis needs no edit to the skill body.

    Measured: copying ``references/qa.md`` to ``references/perf.md`` reds five
    tests in this suite, four of them count claims read straight out of
    SKILL.md. Runtime discovery is real; zero-edit enrollment was not.
    """

    BODY = (REVIEW_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    SIDECAR_TEXT = (REVIEW_SKILL_DIR / "resources" / "axis-selection.md").read_text(
        encoding="utf-8"
    )

    def test_the_body_does_not_claim_enrollment_needs_no_edit(self) -> None:
        assert "no edit to this skill body" not in self.BODY

    def test_the_body_states_that_enrollment_is_not_edit_free(self) -> None:
        assert "Enrollment is not edit-free" in self.BODY

    def test_the_body_still_claims_runtime_discovery(self) -> None:
        # Negative control: the reconciliation must not have deleted the true
        # half of the contract along with the false half. SKILL.md sits within
        # 5 bytes of its 24576-byte size gate, so the detail lives in the
        # sidecar and only the corrected claim stays in the body.
        assert "auto-discovers the axis set from `references/*.md`" in self.BODY

    def test_the_sidecar_names_the_test_that_holds_the_counts_true(self) -> None:
        assert "TestSkillCountClaimsMatchTheCode" in self.SIDECAR_TEXT

    def test_the_named_holder_exists_in_this_module(self) -> None:
        """Positive control: a cross-reference to a test that does not exist
        is worse than no cross-reference."""
        assert "TestSkillCountClaimsMatchTheCode" in globals()


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
