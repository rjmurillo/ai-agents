"""Azure Boards `AB#<n>` references reach the spec gates (issue #5621).

`AB#123` is the GitHub-to-Azure Boards bridge token. Before this change the
extractor read it as nothing, so a pull request that referenced only an Azure
work item set `has_specs=false` and every spec gate evaluated nothing. These
tests pin the contract across the whole path: extractor, loader, report, and
the workflow wiring that joins them.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from scripts.ci import spec_coverage_verdict, spec_extract_refs, spec_load_content  # noqa: E402
from scripts.ci.spec_extract_refs import _extract_azure_refs, _extract_issue_refs  # noqa: E402
from scripts.ci.spec_load_content import EXIT_CONFIG, EXIT_OK  # noqa: E402

_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"


def _read_outputs(path: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        outputs[key] = value
    return outputs


def _extract(tmp_path: Path, body: str, title: str = "feat: change") -> dict[str, str]:
    """Run the extractor entry point and return its step outputs."""
    out_file = tmp_path / "extract-out.txt"
    env = {
        "PR_TITLE_INPUT": title,
        "PR_BODY_INPUT": body,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(out_file),
        "GITHUB_RUN_ID": "0",
    }
    with patch.dict(os.environ, env):
        with patch.object(spec_extract_refs, "_extract_incremental_scope", return_value=(0, "")):
            assert spec_extract_refs.main() == 0
    return _read_outputs(out_file)


class TestExtractAzureRefs:
    """The Azure Boards contract: bare link plus three keyword forms."""

    @pytest.mark.parametrize(
        "body",
        [
            "AB#123",
            "Fixes AB#123",
            "Fixed AB#123",
            "Closed AB#123",
            "See AB#123 for context.",
            "Work item AB#123.",
            "(AB#123)",
            "Fixes: AB#123",
        ],
    )
    def test_each_supported_form_yields_the_literal_token(self, body: str) -> None:
        assert _extract_azure_refs(body) == "AB#123"

    def test_multiple_references_are_sorted_by_number_and_deduplicated(self) -> None:
        body = "AB#200 Fixes AB#9 Closed AB#200 and AB#31"
        assert _extract_azure_refs(body) == "AB#9 AB#31 AB#200"

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "no reference here",
            "AB#0",
            "AB#007",
            "AB#12abc",
            "AB#12_x",
            "AB#",
            "FOOAB#123",
            "ab#123",
            "AB 123",
            "AB#-5",
        ],
    )
    def test_malformed_or_foreign_tokens_yield_nothing(self, body: str) -> None:
        assert _extract_azure_refs(body) == ""

    def test_reference_inside_inline_code_is_ignored(self) -> None:
        assert _extract_azure_refs("Write `AB#123` to link a work item.") == ""

    def test_reference_inside_a_fenced_block_is_ignored(self) -> None:
        assert _extract_azure_refs("```\nFixes AB#123\n```\n") == ""

    def test_real_reference_beside_a_code_span_survives(self) -> None:
        assert _extract_azure_refs("Writing `AB#1` links it. Fixes AB#42") == "AB#42"

    def test_unclosed_fence_masks_through_the_end(self) -> None:
        assert _extract_azure_refs("```\nAB#999") == ""


class TestSourcePlatformsStayApart:
    """GitHub issue syntax and Azure Boards syntax never read each other's tokens."""

    @pytest.mark.parametrize("keyword", ["Fixes", "Fixed", "Closed"])
    def test_ab_token_is_not_a_github_issue_ref(self, keyword: str) -> None:
        assert _extract_issue_refs(f"{keyword} AB#123") == ""

    def test_bare_ab_token_is_not_a_github_issue_ref(self) -> None:
        assert _extract_issue_refs("AB#123") == ""

    @pytest.mark.parametrize("keyword", ["Fixes", "fixed", "fix:"])
    def test_native_ado_style_fixes_is_a_github_issue_here(self, keyword: str) -> None:
        """This extractor reads GitHub text, so `Fixes #123` is a GitHub issue.

        Native Azure Repos resolves the same words against work items. That
        source platform is not read here, so the token must not become an
        Azure Boards ref.
        """
        body = f"{keyword} #123"
        assert _extract_issue_refs(body) == "123"
        assert _extract_azure_refs(body) == ""

    def test_mixed_references_split_by_platform(self) -> None:
        body = "Fixes #42, Fixes owner/repo#7 and Closed AB#900. Also AB#5."
        assert _extract_issue_refs(body) == "42 owner/repo#7"
        assert _extract_azure_refs(body) == "AB#5 AB#900"


class TestRunArmsTheGate:
    def test_ab_only_pull_request_sets_has_specs(self, tmp_path: Path) -> None:
        outputs = _extract(tmp_path, "Fixes AB#123")

        assert outputs["has_specs"] == "true"
        assert outputs["azure_refs"] == "AB#123"
        assert outputs["issue_refs"] == ""
        assert outputs["spec_refs"] == ""

    def test_ab_token_in_the_title_arms_the_gate(self, tmp_path: Path) -> None:
        outputs = _extract(tmp_path, "no refs in body", title="feat: add thing AB#77")

        assert outputs["has_specs"] == "true"
        assert outputs["azure_refs"] == "AB#77"

    def test_mixed_pull_request_reports_both_platforms(self, tmp_path: Path) -> None:
        outputs = _extract(tmp_path, "Fixes #42 and Closed AB#900")

        assert outputs["has_specs"] == "true"
        assert outputs["issue_refs"] == "42"
        assert outputs["azure_refs"] == "AB#900"

    def test_no_reference_still_disarms(self, tmp_path: Path) -> None:
        outputs = _extract(tmp_path, "Nothing linked. AB#0 and AB#abc are not references.")

        assert outputs["has_specs"] == "false"
        assert outputs["azure_refs"] == ""

    def test_code_span_only_ab_token_still_disarms(self, tmp_path: Path) -> None:
        outputs = _extract(tmp_path, "Example: `Fixes AB#123`")

        assert outputs["has_specs"] == "false"


class TestLoaderNeverAsksGithubAboutAzureWorkItems:
    def _load(self, tmp_path: Path, azure_refs: str, issue_refs: str = "") -> tuple[int, str]:
        out_file = tmp_path / "load-out.txt"
        env = {
            "SPEC_REFS": "",
            "ISSUE_REFS": issue_refs,
            "AZURE_REFS": azure_refs,
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        gh = MagicMock(returncode=0, stdout="GitHub issue title\n\nGitHub issue body")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=gh) as run:
                code = spec_load_content.main()
        self.gh_calls = run.call_args_list
        spec_file = tmp_path / "spec-content-0.md"
        return code, spec_file.read_text(encoding="utf-8") if spec_file.exists() else ""

    def test_ab_only_records_traceability_without_calling_gh(self, tmp_path: Path) -> None:
        code, content = self._load(tmp_path, "AB#123")

        assert code == EXIT_OK
        assert self.gh_calls == []
        assert "AB#123" in content
        assert "not loaded" in content
        assert "GitHub issue body" not in content

    def test_multiple_tokens_each_get_a_traceability_part(self, tmp_path: Path) -> None:
        code, content = self._load(tmp_path, "AB#5 AB#900")

        assert code == EXIT_OK
        assert "## Azure Boards AB#5" in content
        assert "## Azure Boards AB#900" in content

    def test_mixed_refs_call_gh_only_for_the_github_issue(self, tmp_path: Path) -> None:
        code, content = self._load(tmp_path, "AB#900", issue_refs="42")

        assert code == EXIT_OK
        assert len(self.gh_calls) == 1
        argv = self.gh_calls[0][0][0]
        assert "42" in argv
        assert not any("AB" in part for part in argv)
        assert "GitHub issue body" in content
        assert "## Azure Boards AB#900" in content

    @pytest.mark.parametrize("raw", ["AB#0", "AB#12abc", "#123", "123", "AB#1\u200b", "ab#1"])
    def test_malformed_token_is_a_config_error(self, tmp_path: Path, raw: str) -> None:
        code, content = self._load(tmp_path, raw)

        assert code == EXIT_CONFIG
        assert self.gh_calls == []
        assert content == ""

    def test_no_azure_refs_is_unchanged(self, tmp_path: Path) -> None:
        code, content = self._load(tmp_path, "", issue_refs="42")

        assert code == EXIT_OK
        assert "Azure Boards" not in content

    def test_nothing_at_all_is_still_a_config_error(self, tmp_path: Path) -> None:
        code, _ = self._load(tmp_path, "")

        assert code == EXIT_CONFIG


def _step(workflow: str, job: str, name: str) -> dict:
    parsed = yaml.safe_load((_WORKFLOWS / workflow).read_text(encoding="utf-8"))
    matches = [s for s in parsed["jobs"][job]["steps"] if s.get("name") == name]
    assert len(matches) == 1, f"expected one {name!r} step in {workflow}, found {len(matches)}"
    return matches[0]


class TestWorkflowWiring:
    """An AB-only pull request reaches the loader, the report, and the verdict."""

    def test_extract_step_output_feeds_the_loader(self) -> None:
        step = _step("ai-spec-review.yml", "review-spec", "Load Spec Content")

        assert step["env"]["AZURE_REFS"] == "${{ steps.spec-ref.outputs.azure_refs }}"
        assert step["run"].strip() == "python3 scripts/ci/spec_load_content.py"

    def test_extract_step_output_feeds_the_report(self) -> None:
        step = _step("ai-spec-review.yml", "review-spec", "Generate Validation Report")

        assert step["env"]["AZURE_REFS"] == "${{ steps.spec-ref.outputs.azure_refs }}"

    def test_loader_and_judges_run_whenever_has_specs_is_true(self) -> None:
        """The guard is `has_specs` alone, so an AB-only pull request is not skipped."""
        for name in ("Load Spec Content", "Prepare Spec Context"):
            step = _step("ai-spec-review.yml", "review-spec", name)
            assert "steps.spec-ref.outputs.has_specs == 'true'" in step["if"]
            assert "azure" not in step["if"].lower()

    def test_verdict_step_reads_has_specs_from_the_same_extractor(self) -> None:
        step = _step("ai-spec-validation.yml", "validate-spec", "Decide spec coverage verdict")

        assert step["env"]["HAS_SPECS"] == "${{ steps.spec-ref.outputs.has_specs }}"

    def test_ab_only_body_reaches_the_validation_path_end_to_end(self, tmp_path: Path) -> None:
        """Chain the real extractor into the real loader, as the workflow does."""
        outputs = _extract(tmp_path, "Fixes AB#123")
        assert outputs["has_specs"] == "true"

        out_file = tmp_path / "chain-load-out.txt"
        env = {
            "SPEC_REFS": outputs["spec_refs"],
            "ISSUE_REFS": outputs["issue_refs"],
            "AZURE_REFS": outputs["azure_refs"],
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_load_content.subprocess.run") as run:
                assert spec_load_content.main() == EXIT_OK
        run.assert_not_called()
        assert "AB#123" in Path(_read_outputs(out_file)["spec_file"]).read_text(encoding="utf-8")

    def test_ab_only_body_is_graded_by_the_required_verdict_check(self, tmp_path: Path) -> None:
        """The required check no longer passes an AB-only pull request as 'no linked spec'."""
        body = "Fixes AB#123"
        has_specs = _extract(tmp_path, body)["has_specs"] == "true"

        verdict = spec_coverage_verdict.decide(has_specs, body)

        assert has_specs
        assert not verdict.passed
        assert "acceptance" in verdict.reason.lower()

    def test_ab_only_body_with_checked_criteria_passes_the_verdict(self, tmp_path: Path) -> None:
        body = "Fixes AB#123\n\n## Acceptance Criteria\n\n- [x] done\n"
        has_specs = _extract(tmp_path, body)["has_specs"] == "true"

        assert spec_coverage_verdict.decide(has_specs, body).passed


def _load_report_module():
    path = _REPO_ROOT / ".github" / "scripts" / "generate_spec_report.py"
    spec = importlib.util.spec_from_file_location("generate_spec_report_azure", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


class TestReportSeparatesPlatforms:
    def _report(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> str:
        module = _load_report_module()
        out = tmp_path / "gh-output"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir()
        argv = [
            "--has-specs", "true",
            "--trace-verdict", "PASS",
            "--completeness-verdict", "PASS",
            "--spec-refs", "",
            "--issue-refs", "42",
            "--trace-findings", "ok",
            "--completeness-findings", "ok",
            "--github-repository", "owner/repo",
            "--server-url", "https://github.com",
            "--run-id", "1",
            "--event-name", "pull_request",
            "--ref-name", "main",
            *extra,
        ]  # fmt: skip
        with patch.object(module, "initialize_ai_review", return_value=str(report_dir)):
            assert module.main(argv) == 0
        return (report_dir / "spec-validation-report.md").read_text(encoding="utf-8")

    def test_report_lists_github_and_azure_refs_in_separate_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = self._report(tmp_path, monkeypatch, "--azure-refs", "AB#5 AB#900")

        assert "| **GitHub issues** | 42 |" in report
        assert "| **Azure Boards** | AB#5 AB#900 |" in report

    def test_report_shows_none_when_there_are_no_azure_refs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = self._report(tmp_path, monkeypatch)

        assert "| **Azure Boards** | *None* |" in report
