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
REFERENCES_DIR = PROJECT_ROOT / ".claude" / "skills" / "review" / "references"

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
    def test_docs_only_change_runs_only_the_always_on_axis(self) -> None:
        result = select(["docs/guide.md", "README.md"])
        assert result["canonical_selected"] == ["analyst"]
        assert result["local_selected"] == []
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

    def test_docs_change_selects_no_local_axis(self) -> None:
        result = select(["docs/guide.md"])
        assert result["local_selected"] == []


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

    SKILL_MD = PROJECT_ROOT / ".claude" / "skills" / "review" / "SKILL.md"

    def test_skill_body_invokes_the_selector_script(self) -> None:
        body = self.SKILL_MD.read_text(encoding="utf-8")
        assert "select_axes.py" in body

    def test_skill_body_names_every_local_axis_selection_rule(self) -> None:
        body = self.SKILL_MD.read_text(encoding="utf-8")
        for axis in mod.LOCAL_AXES:
            assert axis in body, axis

    def test_selection_sidecar_lives_outside_the_axis_references_directory(self) -> None:
        """A reference doc under references/ would enroll a phantom axis."""
        sidecar = PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "axis-selection.md"
        assert sidecar.is_file()
        assert "axis-selection" not in CANDIDATES
        assert not (REFERENCES_DIR / "axis-selection.md").exists()

    def test_sidecar_documents_every_diff_effect_the_script_accepts(self) -> None:
        text = (
            PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "axis-selection.md"
        ).read_text(encoding="utf-8")
        for effect in mod._EFFECT_TABLE:
            assert f"`{effect}`" in text, effect

    def test_six_of_eleven_canonical_prompts_lack_an_applicability_section(self) -> None:
        """Pins the count SKILL.md step 4 cites for why selection is not prose."""
        without = [
            axis
            for axis in CANDIDATES
            if "## When This Axis Applies"
            not in (REFERENCES_DIR / f"{axis}.md").read_text(encoding="utf-8")
        ]
        assert len(CANDIDATES) == 11, CANDIDATES
        assert len(without) == 6, without


@pytest.mark.parametrize(
    ("path", "expected_axis"),
    [
        ("tests/test_router.py", "qa"),
        ("src/auth/login.py", "security"),
        ("uv.lock", "devops"),
        (".github/actions/setup/action.yml", "devops"),
        ("src/models.py", "architect"),
        (".agents/architecture/ADR-099-thing.md", "decision-rigor"),
        (".claude/skills/review/SKILL.md", "agent-safety"),
    ],
)
def test_routing_table_rows_select_their_specialist(path: str, expected_axis: str) -> None:
    result = select([path])
    assert expected_axis in result["canonical_selected"], result["matched_categories"]
