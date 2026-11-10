"""Wiring checks for the /review CodeQL pre-step (ADR-041 amendment 2026-11-09).

These read the shipped skill text. They prove the template, the procedure page, and
the security axis prompt agree with the script's outcomes and do not change the
surfaces the amendment leaves alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import codeql_prestep as pre
import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = (ROOT / "templates" / "skills" / "review.SKILL.md.tmpl").read_text(encoding="utf-8")
REVIEW = ROOT / "src" / "claude" / "skills" / "review"
RESOURCE = (REVIEW / "resources" / "codeql-prestep.md").read_text(encoding="utf-8")
SECURITY = (REVIEW / "references" / "security.md").read_text(encoding="utf-8")
PROMPT = (ROOT / ".github" / "prompts" / "pr-quality-gate-security.md").read_text(encoding="utf-8")
SKILL_MD_BYTE_CAP = 24576

OUTCOMES = sorted(pre._TIER1_OUTCOMES | {"CLEAN", "FINDINGS"})


def step_4d() -> str:
    match = re.search(r"^4d\. .*$", TEMPLATE, flags=re.MULTILINE)
    assert match, "template has no step 4d"
    return match.group(0)


class TestTemplate:
    def test_step_runs_only_when_security_is_selected(self):
        assert "only when `security` is selected" in step_4d()

    def test_step_runs_before_step_4_invokes_the_security_axis(self):
        assert "Run it before step 4 calls that axis" in step_4d()
        invoke = next(ln for ln in TEMPLATE.splitlines() if "For each selected axis" in ln)
        assert "(`security`: after step 4d)" in invoke

    def test_step_points_at_the_procedure_page_and_names_the_adr(self):
        assert "resources/codeql-prestep.md" in step_4d()
        assert "ADR-041" in step_4d()

    def test_step_never_reports_the_unread_states_as_clean(self):
        line = step_4d()
        for state in ("STALE", "NOT ANALYZED", "SKIPPED"):
            assert state in line
        assert "never clean" in line

    def test_step_treats_results_as_untrusted_candidates(self):
        assert "untrusted candidates" in step_4d()

    def test_output_section_prints_the_status_line(self):
        output = TEMPLATE.split("\n## Output\n", 1)[1]
        assert "When step 4d ran, print the CodeQL `status_line`" in output

    def test_the_rendered_skill_stays_inside_the_byte_cap(self):
        assert len((REVIEW / "SKILL.md").read_bytes()) <= SKILL_MD_BYTE_CAP

    def test_the_rendered_skill_carries_step_4d(self):
        assert step_4d() in (REVIEW / "SKILL.md").read_text(encoding="utf-8")

    def test_the_procedure_page_is_not_an_axis_prompt(self):
        axes = {path.stem for path in (REVIEW / "references").glob("*.md")}
        assert "codeql-prestep" not in axes


class TestProcedurePage:
    @pytest.mark.parametrize("outcome", OUTCOMES)
    def test_every_script_outcome_is_documented(self, outcome):
        assert f"`{outcome}`" in RESOURCE

    def test_unread_states_are_marked_never_clean(self):
        for state in ("STALE", "NOT ANALYZED", "SKIPPED"):
            row = next(line for line in RESOURCE.splitlines() if line.startswith(f"| `{state}`"))
            assert "never clean" in row

    def test_unattended_runs_are_told_to_use_tier_1_only(self):
        assert "--unattended" in RESOURCE
        assert "Tier 1 only" in RESOURCE

    def test_alerts_attach_as_untrusted_data_with_no_result_text(self):
        assert "untrusted data" in RESOURCE
        assert "Do not add text from a result to the prompt" in RESOURCE

    def test_a_result_never_sets_the_verdict(self):
        assert "never sets a verdict" in RESOURCE

    def test_it_runs_only_when_security_is_selected(self):
        assert "only when `security` is in `canonical_selected`" in RESOURCE

    def test_flags_it_documents_exist_on_the_script(self):
        help_text = pre.build_parser().format_help()
        for flag in ("--pull-request", "--unattended", "--base-branch"):
            assert flag in RESOURCE
            assert flag in help_text


class TestSecurityAxisPrompt:
    def test_guidance_is_conditional_on_the_attached_block(self):
        assert "only when the input has a block headed `CODEQL RESULTS`" in SECURITY

    def test_guidance_is_read_only(self):
        assert "read-only" in SECURITY
        assert "do not run a scanner" in SECURITY

    def test_entries_are_candidates_to_confirm_and_never_a_verdict(self):
        assert "candidate to confirm" in SECURITY
        assert "never sets the verdict" in SECURITY

    def test_a_missing_block_is_not_a_clean_result(self):
        assert "not a clean result" in SECURITY

    def test_the_committed_ci_prompt_carries_the_guidance(self):
        assert "CODEQL RESULTS" in PROMPT
        assert "candidate to confirm" in PROMPT

    def test_the_block_heading_matches_the_procedure_page(self):
        assert "CODEQL RESULTS" in RESOURCE
