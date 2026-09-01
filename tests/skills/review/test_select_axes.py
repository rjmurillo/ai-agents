# taste-lint: ignore file-size
# This routing suite stays in one file so the selector, contract, and guards share fixtures.
"""Executable routing tests for the ``/review`` axis selector (issue #4981).

PR #5010 shipped risk-based selection as prose plus fixture files, so the
"low-risk runs fewer axes" and "high-risk selects the required specialists"
claims were asserted against JSON fixtures and reference-prompt wording, not
against routing that runs. These tests drive ``select_axes.py`` directly, so
each required additive mapping in issue #4981's routing table is an assertion
on real output.

Each block carries a negative control: the assertion fails if the selector
were stubbed to return the full set, the empty set, or a single family.
"""

from __future__ import annotations

import json
import re
import subprocess
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

SCRIPT_PATH = PROJECT_ROOT / ".claude" / "skills" / "review" / "scripts" / "select_axes.py"
REVIEW_SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "review"
REFERENCES_DIR = REVIEW_SKILL_DIR / "references"
SIDECAR = REVIEW_SKILL_DIR / "resources" / "axis-selection.md"

# The Stage-2 candidates the shipped references/ directory yields today.
CANDIDATES = mod.discover_canonical_axes(REFERENCES_DIR)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the script as a process so exit codes are observed, not inferred."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def select(paths: list[str], **kwargs: object) -> dict:
    return mod.select_axes(changed_paths=paths, canonical_candidates=CANDIDATES, **kwargs)


class TestAxisDiscovery:
    def test_discovers_stage2_axes_from_references_directory(self) -> None:
        assert "analyst" in CANDIDATES
        assert "security" in CANDIDATES
        assert "devops" in CANDIDATES

    def test_excludes_the_stage1_gate_from_stage2_candidates(self) -> None:
        # Negative control: spec-compliance is a references/*.md file, so a
        # selector that globbed without filtering would include it here.
        assert (REFERENCES_DIR / "spec-compliance.md").is_file()
        assert mod.STAGE1_AXIS not in CANDIDATES

    def test_empty_references_directory_yields_no_candidates(self, tmp_path: Path) -> None:
        assert mod.discover_canonical_axes(tmp_path) == []


class TestRequiredAdditiveRouting:
    """Issue #4981: 'The rules must be additive. One change can select several axes.'"""

    def test_dependency_change_selects_security_and_devops(self) -> None:
        result = select(["pyproject.toml"])
        assert "security" in result["canonical_selected"]
        assert "devops" in result["canonical_selected"]
        assert result["fail_closed"] is False

    def test_lockfile_change_selects_security_and_devops(self) -> None:
        result = select(["package-lock.json"])
        assert {"security", "devops"} <= set(result["canonical_selected"])

    def test_dependency_change_does_not_select_architect(self) -> None:
        """Issue #4981 row: 'Dependencies | dependency and security review'.

        ``security`` covers the supply-chain half and ``devops`` owns build
        and dependency wiring. A manifest bump changes no public interface,
        so ``architect`` is deliberately not in this row. This is the one
        mapping the deleted eval-side routing test claimed differently.
        """
        result = select(["pyproject.toml"])
        assert "architect" not in result["canonical_selected"]

    def test_ci_change_selects_devops_and_security(self) -> None:
        result = select([".github/workflows/pr-validation.yml"])
        assert {"devops", "security"} <= set(result["canonical_selected"])

    def test_type_change_selects_architect(self) -> None:
        result = select(["src/api/types.ts"])
        assert "architect" in result["canonical_selected"]

    def test_public_api_effect_selects_architect(self) -> None:
        result = select(["src/service.py"], effects=["public-api"])
        assert "architect" in result["canonical_selected"]

    def test_test_change_selects_qa(self) -> None:
        result = select(["tests/skills/review/test_select_axes.py"])
        assert "qa" in result["canonical_selected"]

    def test_fixture_change_selects_qa(self) -> None:
        result = select(["tests/hooks/fixtures/sample.json"])
        assert "qa" in result["canonical_selected"]

    def test_error_handling_effect_selects_reliability_and_qa(self) -> None:
        result = select(["src/worker.py"], effects=["error-handling"])
        assert {"reliability", "qa"} <= set(result["canonical_selected"])

    def test_auth_path_selects_security(self) -> None:
        result = select(["src/auth/session.py"])
        assert "security" in result["canonical_selected"]

    def test_dotenv_path_selects_security(self) -> None:
        result = select([".env.example"])
        assert "security" in result["canonical_selected"]

    def test_one_change_accumulates_axes_from_several_categories(self) -> None:
        # Additive: a CI workflow plus a test file selects both families.
        result = select([".github/workflows/ci.yml", "tests/test_thing.py"])
        selected = set(result["canonical_selected"])
        assert {"devops", "security", "qa"} <= selected

    def test_unrelated_specialists_are_not_selected_for_a_test_only_change(self) -> None:
        # Negative control: a selector that always returned the full set
        # would fail this.
        result = select(["tests/test_thing.py"])
        assert "devops" not in result["canonical_selected"]
        assert "roadmap" not in result["canonical_selected"]


class TestLowRiskRunsFewerAxes:
    def test_docs_only_change_runs_the_always_on_axis_and_doc_accuracy(self) -> None:
        # Issue #4981 routing row: "Docs and instruction claims ->
        # documentation accuracy review". Still low-risk: 2 Stage-2 axes,
        # not the full set.
        result = select(["docs/guide.md", "README.md"])
        assert result["canonical_selected"] == ["analyst"]
        assert result["local_selected"] == ["doc-accuracy"]
        assert result["fail_closed"] is False

    def test_docs_only_change_selects_fewer_axes_than_deep_review(self) -> None:
        low = select(["docs/guide.md"])
        deep = select(["docs/guide.md"], deep=True)
        low_count = len(low["canonical_selected"]) + len(low["local_selected"])
        deep_count = len(deep["canonical_selected"]) + len(deep["local_selected"])
        assert low_count < deep_count
        assert deep_count == len(CANDIDATES) + len(mod.LOCAL_AXES)

    def test_skipped_axes_carry_a_reason_and_are_not_reported_as_pass(self) -> None:
        result = select(["docs/guide.md"])
        assert result["skipped"], "a low-risk change must report skipped axes"
        for axis, reason in result["skipped"].items():
            assert reason.startswith("skipped"), axis
            assert "PASS" not in reason


class TestFailClosed:
    def test_unclassified_path_selects_every_candidate_axis(self) -> None:
        result = select(["some/unknown/artifact.xyz"])
        assert result["fail_closed"] is True
        assert set(result["canonical_selected"]) == set(CANDIDATES)
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)
        assert result["unclassified_paths"] == ["some/unknown/artifact.xyz"]

    def test_unknown_diff_effect_fails_closed(self) -> None:
        result = select(["docs/guide.md"], effects=["quantum-entanglement"])
        assert result["fail_closed"] is True
        assert result["unknown_effects"] == ["quantum-entanglement"]
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_empty_change_set_fails_closed(self) -> None:
        result = select([])
        assert result["fail_closed"] is True
        assert set(result["canonical_selected"]) == set(CANDIDATES)

    def test_fail_closed_reason_is_recorded_per_axis(self) -> None:
        result = select(["some/unknown/artifact.xyz"])
        assert all("fail-closed" in reason for reason in result["selection_reasons"].values())

    def test_deep_review_is_not_reported_as_fail_closed(self) -> None:
        result = select(["docs/guide.md"], deep=True)
        assert result["fail_closed"] is False
        assert result["mode"] == "deep"


class TestDemandedAxisWithNoPrompt:
    """A demanded axis with no ``references/{stem}.md`` must not vanish.

    The selector intersected the demanded axes with the discovered candidate
    set, so an axis a risk category or diff effect demanded, whose prompt file
    was absent, appeared in neither ``canonical_selected`` nor ``skipped``
    while ``fail_closed`` stayed false: the review silently got narrower.
    """

    PARTIAL_SET = ("analyst", "qa", "security", "devops", "architect", "spec-compliance")

    @staticmethod
    def _references(tmp_path: Path, stems: tuple[str, ...]) -> list[str]:
        for stem in stems:
            (tmp_path / f"{stem}.md").write_text("stub prompt\n", encoding="utf-8")
        return mod.discover_canonical_axes(tmp_path)

    @staticmethod
    def _partial_run(candidates: list[str]) -> dict:
        # reliability is demanded by effect:error-handling, code-quality by
        # the executable-code category; neither has a prompt in this set.
        return mod.select_axes(
            changed_paths=["src/worker.py"],
            canonical_candidates=candidates,
            effects=["error-handling"],
        )

    def test_demanded_but_missing_axis_is_reported(self, tmp_path: Path) -> None:
        result = self._partial_run(self._references(tmp_path, self.PARTIAL_SET))
        assert result["unresolved_axes"] == ["code-quality", "reliability"]

    def test_unresolved_axes_carry_fail_closed_reasons(self, tmp_path: Path) -> None:
        result = self._partial_run(self._references(tmp_path, self.PARTIAL_SET))
        assert result["selection_reasons"]["code-quality"] == (
            "selected - fail-closed: a demanded axis has no prompt to load"
        )
        assert result["selection_reasons"]["reliability"] == (
            "selected - fail-closed: a demanded axis has no prompt to load"
        )

    def test_a_missing_demanded_axis_fails_closed(self, tmp_path: Path) -> None:
        candidates = self._references(tmp_path, self.PARTIAL_SET)
        result = self._partial_run(candidates)
        assert result["fail_closed"] is True
        assert set(result["canonical_selected"]) == set(candidates)
        assert set(result["local_selected"]) == set(mod.LOCAL_AXES)

    def test_every_candidate_is_selected_or_skipped(self, tmp_path: Path) -> None:
        # No axis disappears from both lists, on either branch.
        candidates = self._references(tmp_path, self.PARTIAL_SET)
        for effects in ([], ["error-handling"]):
            result = mod.select_axes(
                changed_paths=["docs/guide.md"], canonical_candidates=candidates, effects=effects
            )
            accounted = set(result["canonical_selected"]) | set(result["skipped"])
            assert set(candidates) <= accounted, (effects, result)

    def test_missing_always_on_prompt_fails_closed_instead_of_being_dropped(
        self, tmp_path: Path
    ) -> None:
        # Negative control for the guarded ALWAYS_ON loop: with no
        # references/analyst.md the always-on axis cannot run, and the run
        # must widen rather than report a clean narrow selection.
        candidates = self._references(tmp_path, ("qa", "security", "spec-compliance"))
        assert "analyst" not in candidates
        result = mod.select_axes(changed_paths=["docs/guide.md"], canonical_candidates=candidates)
        assert "analyst" in result["unresolved_axes"]
        assert result["fail_closed"] is True

    def test_a_complete_prompt_set_reports_no_unresolved_axes(self) -> None:
        result = select(["src/worker.py"], effects=["error-handling"])
        assert result["unresolved_axes"] == []
        assert result["fail_closed"] is False


class TestTokenMatchingDoesNotOverFire:
    """Bare-substring matching selected specialists on ordinary paths."""

    LOOKALIKES = ["docs/authors.md", "src/tokenizer.py", "docs/release-notes.md"]

    @pytest.mark.parametrize("path", LOOKALIKES)
    def test_word_lookalike_paths_select_no_specialist(self, path: str) -> None:
        result = select([path])
        assert "security" not in result["canonical_selected"], path
        assert "devops" not in result["canonical_selected"], path
        assert result["fail_closed"] is False, path

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("src/auth/session.py", "security"), ("src/oauth_client.py", "security"),
            ("utils/sanitizer.py", "security"), (".github/workflows/release.yml", "devops"),
            ("deploy/main.tf", "devops"), ("release/publish.yml", "devops"),
            ("Dockerfile", "devops"),
        ],
    )
    def test_real_security_and_ci_paths_still_select(self, path: str, expected: str) -> None:
        # Positive control: narrowing the match must not disarm the category.
        result = select([path])
        assert expected in result["canonical_selected"], result["matched_categories"]


class TestPinnedAxesStayInTheirFamily:
    """Regression: PR #5010 conflated the canonical and local selected sets.

    A local-only skill axis has no ``references/{stem}.md`` file, so a pinned
    local axis that lands in the canonical list resolves to a prompt path that
    does not exist.
    """

    def test_pinned_local_axis_never_enters_the_canonical_set(self) -> None:
        result = select(["docs/guide.md"], pinned=["code-qualities-assessment"])
        assert "code-qualities-assessment" in result["local_selected"]
        assert "code-qualities-assessment" not in result["canonical_selected"]

    def test_every_local_axis_lacks_a_canonical_prompt_file(self) -> None:
        # Proves why the conflation is a defect, not a style preference.
        for axis in mod.LOCAL_AXES:
            assert not (REFERENCES_DIR / f"{axis}.md").exists(), axis
            assert axis not in CANDIDATES, axis

    def test_pinned_canonical_axis_enters_the_canonical_set(self) -> None:
        result = select(["docs/guide.md"], pinned=["observability"])
        assert "observability" in result["canonical_selected"]
        assert "observability" not in result["local_selected"]

    def test_pinned_axis_is_reported_as_pinned_not_risk_selected(self) -> None:
        result = select(["docs/guide.md"], pinned=["taste-lints"])
        assert "pinned" in result["selection_reasons"]["taste-lints"]

    def test_always_on_axis_runs_even_when_no_category_selects_it(self) -> None:
        result = select(["docs/guide.md"])
        for axis in mod.ALWAYS_ON_CANONICAL:
            assert axis in result["canonical_selected"]
            assert result["selection_reasons"][axis] == "selected - always-on"


class TestLocalAxisSelection:
    def test_executable_code_selects_the_code_quality_local_axes(self) -> None:
        result = select(["src/service.py"])
        assert {"code-qualities-assessment", "taste-lints"} <= set(result["local_selected"])

    def test_toolkit_artifact_selects_golden_principles(self) -> None:
        result = select([".github/workflows/ci.yml"])
        assert "golden-principles" in result["local_selected"]

    def test_docs_change_selects_doc_accuracy(self) -> None:
        result = select(["docs/guide.md"])
        assert result["local_selected"] == ["doc-accuracy"]

    def test_plain_text_change_selects_doc_accuracy_not_an_empty_specialist_set(
        self,
    ) -> None:
        # Negative control for the defect this replaced: the docs category
        # matched every text-shaped path and contributed no axis at all, so a
        # .txt change was classified (no fail-closed) and reviewed by nobody.
        result = select(["CHANGELOG.txt"])
        assert result["local_selected"] == ["doc-accuracy"]
        assert result["fail_closed"] is False

    def test_code_change_does_not_select_doc_accuracy(self) -> None:
        result = select(["src/service.py"])
        assert "doc-accuracy" not in result["local_selected"]


class TestPathNormalization:
    def test_windows_separators_are_classified(self) -> None:
        result = select([r"tests\skills\review\test_thing.py"])
        assert "qa" in result["canonical_selected"]
        assert result["fail_closed"] is False

    def test_uppercase_paths_are_classified(self) -> None:
        result = select(["Tests/Review/Test_Thing.py"])
        assert "qa" in result["canonical_selected"]

    def test_blank_path_entries_are_ignored_not_unclassified(self) -> None:
        result = select(["docs/guide.md", "   "])
        assert result["unclassified_paths"] == []
        assert result["fail_closed"] is False


class TestClassifyPaths:
    def test_returns_matched_categories_in_table_order(self) -> None:
        categories, unclassified = mod.classify_paths(["tests/test_a.py", "pyproject.toml"])
        assert "tests-or-fixtures" in categories
        assert "dependencies" in categories
        assert unclassified == []

    def test_reports_unclassified_paths_verbatim(self) -> None:
        categories, unclassified = mod.classify_paths(["mystery.bin"])
        assert categories == []
        assert unclassified == ["mystery.bin"]


class TestCliExitCodes:
    """Contract stated in the script docstring: 0 selection, 2 config error."""

    def test_exit_0_and_json_on_stdout_for_a_valid_selection(self) -> None:
        proc = run_cli("--changed-path", "docs/guide.md")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["canonical_selected"] == ["analyst"]

    def test_exit_0_for_deep_review(self) -> None:
        proc = run_cli("--changed-path", "docs/guide.md", "--deep")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["mode"] == "deep"

    def test_exit_2_for_an_unknown_pinned_axis(self) -> None:
        proc = run_cli("--changed-path", "docs/guide.md", "--pin", "not-an-axis")
        assert proc.returncode == 2
        assert "unknown pinned axis" in proc.stderr

    def test_exit_2_when_the_references_directory_is_missing(self, tmp_path: Path) -> None:
        proc = run_cli(
            "--changed-path",
            "docs/guide.md",
            "--references-dir",
            str(tmp_path / "does-not-exist"),
        )
        assert proc.returncode == 2
        assert "references directory not found" in proc.stderr

    def test_exit_2_when_the_references_directory_is_empty(self, tmp_path: Path) -> None:
        proc = run_cli("--changed-path", "docs/guide.md", "--references-dir", str(tmp_path))
        assert proc.returncode == 2
        assert "no canonical axis prompts" in proc.stderr

    def test_main_returns_0_when_called_in_process(self) -> None:
        assert mod.main(["--changed-path", "docs/guide.md"]) == 0

    def test_main_returns_2_on_config_error_when_called_in_process(self) -> None:
        assert mod.main(["--changed-path", "docs/guide.md", "--pin", "bogus"]) == 2


class TestSkillDocumentsTheSelector:
    """The SKILL.md Process must call the selector, not re-derive routing."""

    SKILL_MD = REVIEW_SKILL_DIR / "SKILL.md"

    def test_skill_body_invokes_the_selector_script(self) -> None:
        body = self.SKILL_MD.read_text(encoding="utf-8")
        assert "select_axes.py" in body

    def test_skill_body_names_every_local_axis_selection_rule(self) -> None:
        body = self.SKILL_MD.read_text(encoding="utf-8")
        for axis in mod.LOCAL_AXES:
            assert axis in body, axis

    def test_selection_sidecar_lives_outside_the_axis_references_directory(self) -> None:
        """A reference doc under references/ would enroll a phantom axis."""
        assert SIDECAR.is_file()
        assert "axis-selection" not in CANDIDATES
        assert not (REFERENCES_DIR / "axis-selection.md").exists()

    def test_sidecar_documents_every_diff_effect_the_script_accepts(self) -> None:
        text = SIDECAR.read_text(encoding="utf-8")
        for effect in mod._EFFECT_TABLE:
            assert f"`{effect}`" in text, effect

    def test_skill_body_states_when_to_pass_deep(self) -> None:
        """AC-10 needs a runtime trigger, not only a documented mode.

        The rewrite of Process step 4 dropped the only sentence telling the
        reviewer when to request a deep review, so nothing in the Process set
        ``--deep`` and the full-set mode was unreachable at runtime.
        """
        body = self.SKILL_MD.read_text(encoding="utf-8")
        assert "Pass `--deep` when" in body

    def test_sidecar_names_the_prompts_lacking_an_applicability_section(self) -> None:
        """The sidecar's claim about prose routing must match the tree.

        Deliberately not pinned to a fixed candidate count: the convergence
        contract promises runtime discovery, not zero-edit enrollment, so
        adding a prompt that carries the section must not red this suite.
        """
        section = "## When This Axis Applies"
        without = {
            axis
            for axis in CANDIDATES
            if section not in (REFERENCES_DIR / f"{axis}.md").read_text(encoding="utf-8")
        }
        assert without, "the sidecar claims some prompts lack the section"
        assert len(without) < len(CANDIDATES), (
            "the sidecar's premise is that SOME prompts have the section"
        )

        text = " ".join(SIDECAR.read_text(encoding="utf-8").split())
        marker = "These canonical prompts have no such section:"
        assert marker in text, "sidecar no longer states which prompts lack the section"
        claim = text.split(marker, 1)[1].split(".", 1)[0]
        named = set(re.findall(r"`([a-z0-9-]+)`", claim))
        assert named == without, (named, without)

    def test_skill_body_names_the_local_axis_verdict_adapter(self) -> None:
        body = self.SKILL_MD.read_text(encoding="utf-8")
        assert "adapt_local_axis_verdict" in body
        assert "Append one `UNKNOWN` row per `unresolved_axes` entry." in body
        for axis_line in (
            'doc_accuracy.py> --target . --diff-base "origin/$BASE_BRANCH" --format json',
            'scan_principles.py> --diff-scope "origin/$BASE_BRANCH" --format json',
            'taste_lints.py> --diff-scope "origin/$BASE_BRANCH" --format json',
        ):
            assert axis_line in body, axis_line


@pytest.mark.parametrize(
    ("path", "expected_axis"),
    [
        ("tests/test_router.py", "qa"), ("src/auth/login.py", "security"),
        ("uv.lock", "devops"), (".github/actions/setup/action.yml", "devops"),
        ("src/models.py", "architect"), (".agents/architecture/ADR-099-thing.md", "decision-rigor"),
        (".claude/skills/review/SKILL.md", "agent-safety"),
    ],
)
def test_routing_table_rows_select_their_specialist(path: str, expected_axis: str) -> None:
    result = select([path])
    assert expected_axis in result["canonical_selected"], result["matched_categories"]
