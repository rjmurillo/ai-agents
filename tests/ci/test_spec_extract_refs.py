"""Tests for scripts/ci/spec_extract_refs.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_extract_refs import (
    EXIT_EXTERNAL,
    EXIT_OK,
    _extract_incremental_scope,
    _extract_issue_refs,
    _extract_spec_refs,
    main,
    run,
)


class TestExtractSpecRefs:
    def test_extracts_req_ids(self) -> None:
        result = _extract_spec_refs("See REQ-001 and REQ-042 for details")
        assert "REQ-001" in result
        assert "REQ-042" in result

    def test_extracts_design_ids(self) -> None:
        result = _extract_spec_refs("Implements DESIGN-007")
        assert "DESIGN-007" in result

    def test_extracts_task_ids(self) -> None:
        result = _extract_spec_refs("Closes TASK-123")
        assert "TASK-123" in result

    def test_extracts_spec_file_paths(self) -> None:
        result = _extract_spec_refs("See .agents/specs/my-spec.md for details")
        assert ".agents/specs/my-spec.md" in result

    def test_extracts_planning_paths(self) -> None:
        result = _extract_spec_refs("Plan: .agents/planning/sprint.md")
        assert ".agents/planning/sprint.md" in result

    def test_empty_string_returns_empty(self) -> None:
        assert _extract_spec_refs("no references here") == ""

    def test_backticked_spec_path_still_counts(self) -> None:
        """`.github/PULL_REQUEST_TEMPLATE.md` writes spec paths in backticks.

        The code-span mask applies to issue refs only. Masking here would
        disarm the gate on the template's own convention.
        """
        result = _extract_spec_refs("| **Spec** | `.agents/planning/sprint.md` |")
        assert ".agents/planning/sprint.md" in result

    def test_deduplicates(self) -> None:
        refs = _extract_spec_refs("REQ-001 REQ-001 REQ-002")
        parts = refs.split()
        assert parts.count("REQ-001") == 1


class TestExtractIssueRefs:
    def test_extracts_fixes_ref(self) -> None:
        result = _extract_issue_refs("Fixes #42")
        assert "42" in result

    def test_extracts_closes_ref(self) -> None:
        result = _extract_issue_refs("Closes #100")
        assert "100" in result

    def test_extracts_cross_repo_ref(self) -> None:
        result = _extract_issue_refs("Implements owner/repo#55")
        assert "owner/repo#55" in result

    def test_no_refs_returns_empty(self) -> None:
        assert _extract_issue_refs("no references") == ""

    def test_deduplicates(self) -> None:
        result = _extract_issue_refs("Fixes #5 Fixes #5")
        parts = result.split()
        assert parts.count("5") == 1

    # Issue #5620: GitHub resolves every tense of every closing keyword, in any
    # case. Each spelling the parser missed produced has_specs=false and a
    # required check that judged nothing.
    @pytest.mark.parametrize(
        "keyword",
        [
            "close",
            "closes",
            "closed",
            "fix",
            "fixes",
            "fixed",
            "resolve",
            "resolves",
            "resolved",
        ],
    )
    def test_extracts_every_github_closing_keyword(self, keyword: str) -> None:
        assert _extract_issue_refs(f"{keyword} #123") == "123"
        assert _extract_issue_refs(f"{keyword.upper()} #123") == "123"
        assert _extract_issue_refs(f"{keyword.capitalize()} #123") == "123"

    @pytest.mark.parametrize(
        "body",
        ["Closes: #10", "closes:#10", "CLOSES:  #10", "Fixes:\n#10"],
    )
    def test_extracts_colon_syntax(self, body: str) -> None:
        assert _extract_issue_refs(body) == "10"

    @pytest.mark.parametrize(
        "body",
        [
            "Fixes owner/repo.name#123",
            "Fixes my-org/my-repo#123",
            "Fixes owner/repo_name#123",
        ],
    )
    def test_extracts_cross_repo_names_with_dots_and_hyphens(self, body: str) -> None:
        assert _extract_issue_refs(body).endswith("#123")

    # Issue #5489: universal.md MUST 2 and MUST 3 tell the author to write
    # `Refs #<n>` when the change does not close the issue, and that spelling
    # was the one that disarmed the gate.
    @pytest.mark.parametrize(
        "body",
        ["Refs #4789", "refs #4789", "Ref #4789", "REFS: #4789", "Part of #4789"],
    )
    def test_extracts_non_closing_linkage(self, body: str) -> None:
        assert _extract_issue_refs(body) == "4789"

    @pytest.mark.parametrize(
        "body",
        [
            "prefixes #42",
            "postfixed #42",
            "See #42",
            "issue #42",
            "Fixes #",
            "Fixes 42",
            "#42",
        ],
    )
    def test_ignores_text_that_is_not_issue_linkage(self, body: str) -> None:
        assert _extract_issue_refs(body) == ""

    def test_deduplicates_across_keywords(self) -> None:
        assert _extract_issue_refs("Fixes #7\nRefs #7") == "7"

    # PR #5648's own run reported `ISSUE_REFS: 10 5489 5600 5620 5621 5623`
    # from a body that only linked three issues. The other three came from
    # backticked examples in the prose, two of them pull request numbers, and
    # the loader handed all six to the judge as this PR's requirements.
    @pytest.mark.parametrize(
        "body",
        [
            "See `Fixes #42` for the syntax",
            "The old pattern was ``Closes: #42`` in prose",
            "```\nFixes #42\n```",
            "```python\n# Closes #42\n```",
            "~~~\nRefs #42\n~~~",
            "```\nFixes #42\n",
        ],
    )
    def test_ignores_references_inside_code(self, body: str) -> None:
        assert _extract_issue_refs(body) == ""

    def test_keeps_a_real_reference_beside_a_code_span(self) -> None:
        body = "Writing `Refs #99` is the honest form. Fixes #42"
        assert _extract_issue_refs(body) == "42"

    def test_pr_5648_body_shape(self) -> None:
        """Regression fixture taken from the body that produced the defect."""
        body = (
            "The other misses (`closed`, `Closes: #10`, `owner/repo.name#10`) "
            "opened the same hole.\n\n"
            "```python\n"
            'r"(?:Closes|Fixes|Resolves|Implements)\\s+(#\\d+)"\n'
            "```\n\n"
            "| **Issue** | Fixes #5489 | `Refs #n` disarms the judge |\n"
            "| **Issue** | Fixes #5620 | missed variants |\n\n"
            "`AB#` work-item tokens (#5621) are out of scope.\n\n"
            "PR #5609 carries `Refs #5600` and PR #5630 carries `Refs #5623`.\n\n"
            "## Related Issues\n\nFixes #5489\nFixes #5620\nRefs #5621\n"
        )
        assert _extract_issue_refs(body) == "5489 5620 5621"

    # Devin Review on PR #5648 found the regex mask wrong in both delimiter
    # directions. A fence closes on a run of the same character at least as long
    # as the opener, so a three-backtick opener closed by four ran to the end of
    # the body and masked every later reference: the same has_specs=false
    # fail-open this file exists to close.
    @pytest.mark.parametrize(
        "body",
        [
            "```\ncode\n````\n\nFixes #5489\n",
            "~~~\ncode\n~~~~~\n\nFixes #5489\n",
            '```python\nr"Fixes #99"\n``````\n\nFixes #5489\n',
        ],
    )
    def test_fence_closes_on_a_longer_run_of_the_same_character(self, body: str) -> None:
        assert _extract_issue_refs(body) == "5489"

    def test_unclosed_fence_masks_through_the_end(self) -> None:
        assert _extract_issue_refs("```\nFixes #999\nFixes #888") == ""

    # A code span closes on a backtick run of exactly the opener's length and may
    # contain shorter runs. The old mask ended the span at the inner run and
    # exposed the example reference as prose.
    def test_code_span_may_contain_a_shorter_backtick_run(self) -> None:
        body = "``a ` Fixes #999`` and really Fixes #5489"
        assert _extract_issue_refs(body) == "5489"

    def test_unmatched_backtick_is_literal_text(self) -> None:
        assert _extract_issue_refs("a ` stray tick, Fixes #5489") == "5489"

    # Masked content becomes NUL, not a space, so the keyword-to-reference
    # separator cannot bridge across what was removed.
    @pytest.mark.parametrize(
        "body",
        ["Fixes `x` #12", "Fixes\n```\ncode\n```\n#12"],
    )
    def test_masking_does_not_create_a_link_the_body_never_had(self, body: str) -> None:
        assert _extract_issue_refs(body) == ""

    # `#\d+` with no trailing guard read `Refs #4054garbage` as issue 4054 and
    # loaded an unrelated issue into the judge's context.
    @pytest.mark.parametrize(
        "body",
        ["Refs #4054garbage", "Refs #0", "Refs #007", "Fixes #12_a", "Refs #0000"],
    )
    def test_rejects_malformed_reference_numbers(self, body: str) -> None:
        assert _extract_issue_refs(body) == ""

    def test_sentence_punctuation_after_a_reference_still_links(self) -> None:
        body = "Fixes #12. Also Fixes #13, and Fixes #14; plus Fixes #15)"
        assert sorted(_extract_issue_refs(body).split()) == ["12", "13", "14", "15"]

    def test_collects_every_reference_in_a_multi_ref_body(self) -> None:
        body = "Refs #5574\nRefs #5624\nCloses #5610"
        assert sorted(_extract_issue_refs(body).split()) == ["5574", "5610", "5624"]


class TestExtractIncrementalScope:
    def test_returns_stdout_on_success(self) -> None:
        mock = MagicMock(returncode=0, stdout="phase-1\n")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: phase-1 impl") == (EXIT_OK, "phase-1")

    def test_returns_external_error_on_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="", stderr="parser failed")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: unknown") == (EXIT_EXTERNAL, "")


class TestRun:
    def test_has_specs_false_when_no_refs(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "chore: bump version",
            "PR_BODY_INPUT": "No spec here.",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                return_value=MagicMock(returncode=0, stdout=""),
            ):
                rc = run()
        assert rc == 0
        assert "has_specs=false" in out_file.read_text()

    def test_has_specs_true_when_refs_found(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "feat: implement REQ-001",
            "PR_BODY_INPUT": "Fixes #10",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                return_value=MagicMock(returncode=0, stdout=""),
            ):
                run()
        assert "has_specs=true" in out_file.read_text()

    @pytest.mark.parametrize(
        "body",
        ["Refs #4789", "CLOSES: #123", "closed #123", "Part of #123"],
    )
    def test_has_specs_true_for_linkage_the_old_parser_missed(
        self, body: str, tmp_path: Path
    ) -> None:
        """Pin the workflow guard, not the helper return value.

        `.github/workflows/ai-spec-validation.yml` gates every judging step on
        `steps.spec-ref.outputs.has_specs == 'true'`, so the output file is the
        contract that decides whether the required check evaluates anything.
        Issues #5489 and #5620.
        """
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "fix(ci): a change with no spec ID in the title",
            "PR_BODY_INPUT": body,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                return_value=MagicMock(returncode=0, stdout=""),
            ):
                assert run() == 0
        assert "has_specs=true" in out_file.read_text()

    def test_fallback_to_gh_when_no_inputs(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "",
            "PR_BODY_INPUT": "",
            "PR_NUMBER": "7",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        gh_mock = MagicMock(returncode=0, stdout="title text")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=gh_mock):
                rc = run()
        assert rc == 0

    def test_incremental_scope_failure_main_returns_external(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "feat: Phase 2 of #100",
            "PR_BODY_INPUT": "Fixes #10",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        failure = MagicMock(returncode=1, stdout="", stderr="parser failed")

        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=failure):
                assert main() == EXIT_EXTERNAL

        assert not out_file.exists()

    def test_pr_lookup_failure_main_returns_external(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "",
            "PR_BODY_INPUT": "",
            "PR_NUMBER": "7",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        failure = MagicMock(returncode=1, stdout="", stderr="API unavailable")

        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=failure):
                assert main() == EXIT_EXTERNAL

    def test_pr_lookup_launch_failure_main_returns_external(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "",
            "PR_BODY_INPUT": "",
            "PR_NUMBER": "7",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                side_effect=OSError("gh not found"),
            ):
                assert main() == EXIT_EXTERNAL

    def test_scope_parser_launch_failure_main_returns_external(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "feat: Phase 2 of #100",
            "PR_BODY_INPUT": "Fixes #10",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                side_effect=OSError("python not found"),
            ):
                assert main() == EXIT_EXTERNAL


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_extract_refs.run", return_value=0):
            assert main() == 0
