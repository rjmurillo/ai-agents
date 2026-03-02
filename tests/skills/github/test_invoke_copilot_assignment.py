"""Tests for invoke_copilot_assignment.py."""

import json
import os
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "invoke_copilot_assignment"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestHelpers:
    def test_get_maintainer_guidance_bullets(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "- Use the new API endpoint\n- Check error handling",
        }]
        result = mod.get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(result) == 2
        assert "Use the new API endpoint" in result[0]

    def test_get_maintainer_guidance_rfc_keywords(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "This implementation MUST handle edge cases properly.",
        }]
        result = mod.get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(result) >= 1

    def test_get_maintainer_guidance_no_maintainer_comments(self, _import_module):
        mod = _import_module
        comments = [{"user": {"login": "other"}, "body": "hello"}]
        result = mod.get_maintainer_guidance(comments, ["rjmurillo"])
        assert result == []

    def test_get_coderabbit_plan_with_implementation(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "coderabbitai[bot]"},
            "body": "## Implementation\nDo X then Y\n## Other",
        }]
        patterns = {
            "username": "coderabbitai[bot]",
            "implementation_plan": "## Implementation",
            "related_issues": "Related Issues",
            "related_prs": "Related PRs",
        }
        result = mod.get_coderabbit_plan(comments, patterns)
        assert result is not None
        assert "Do X then Y" in result["Implementation"]

    def test_get_coderabbit_plan_no_comments(self, _import_module):
        mod = _import_module
        result = mod.get_coderabbit_plan([], {
            "username": "coderabbitai[bot]",
            "implementation_plan": "## Implementation",
            "related_issues": "",
            "related_prs": "",
        })
        assert result is None

    def test_get_ai_triage_info_table_format(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "bot"},
            "body": "<!-- AI-ISSUE-TRIAGE -->\n| **Priority** | `P1` |\n| **Category** | `bug` |",
        }]
        result = mod.get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result["Priority"] == "P1"
        assert result["Category"] == "bug"

    def test_get_ai_triage_info_plain_format(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "bot"},
            "body": "<!-- AI-ISSUE-TRIAGE -->\nPriority: P2\nCategory: enhancement",
        }]
        result = mod.get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result["Priority"] == "P2"

    def test_get_ai_triage_info_no_marker(self, _import_module):
        mod = _import_module
        comments = [{"user": {"login": "x"}, "body": "nothing here"}]
        result = mod.get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result is None


class TestHasSynthesizableContent:
    def test_with_guidance(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content(["item"], None, None) is True

    def test_with_triage(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content(
            [], None, {"Priority": "P1", "Category": None}
        ) is True

    def test_with_coderabbit_implementation(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content(
            [], {"Implementation": "do X", "RelatedIssues": [], "RelatedPRs": []},
            None,
        ) is True

    def test_empty(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content([], None, None) is False

    def test_triage_with_empty_strings(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content(
            [], None, {"Priority": "", "Category": ""}
        ) is False

    def test_triage_with_whitespace(self, _import_module):
        mod = _import_module
        assert mod.has_synthesizable_content(
            [], None, {"Priority": "  ", "Category": None}
        ) is False


class TestBuildSynthesisComment:
    def test_includes_marker_and_copilot(self, _import_module):
        mod = _import_module
        body = mod.build_synthesis_comment(
            "<!-- MARKER -->", ["guidance item"], None, None,
        )
        assert "<!-- MARKER -->" in body
        assert "@copilot" in body
        assert "guidance item" in body

    def test_includes_ai_triage(self, _import_module):
        mod = _import_module
        body = mod.build_synthesis_comment(
            "<!-- M -->", [],
            None, {"Priority": "P0", "Category": "bug"},
        )
        assert "**Priority**: P0" in body
        assert "**Category**: bug" in body


class TestInvokeCopilotAssignment:
    def test_prepare_context_only(self, _import_module, tmp_path):
        mod = _import_module
        issue = {"title": "Test", "body": "body", "labels": []}
        comments = []

        with (
            patch.object(mod, "_run_gh") as mock_gh,
            patch.object(mod, "_get_comments", return_value=comments),
        ):
            mock_gh.return_value = make_completed_process(
                stdout=json.dumps(issue)
            )
            result = mod.invoke_copilot_assignment(
                "o", "r", 1, prepare_context_only=True,
            )

        assert result["Success"] is True
        assert result["ContextFile"].endswith("issue-1-context.md")
        assert os.path.isfile(result["ContextFile"])
        os.unlink(result["ContextFile"])

    def test_dry_run(self, _import_module):
        mod = _import_module
        issue = {"title": "Test", "body": "body", "labels": []}

        with (
            patch.object(mod, "_run_gh") as mock_gh,
            patch.object(mod, "_get_comments", return_value=[]),
        ):
            mock_gh.return_value = make_completed_process(
                stdout=json.dumps(issue)
            )
            result = mod.invoke_copilot_assignment(
                "o", "r", 1, dry_run=True,
            )

        assert result["Action"] == "DryRun"

    def test_issue_not_found_exits_2(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                stdout="Not Found", returncode=1,
            )
            with pytest.raises(SystemExit) as exc:
                mod.invoke_copilot_assignment("o", "r", 999)

        assert exc.value.code == 2
