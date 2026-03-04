"""Tests for invoke_copilot_assignment.py."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure scripts are importable
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "issue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402

from test_helpers import make_completed_process  # noqa: E402


@pytest.fixture
def _import_module():
    import importlib
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
        result = mod._get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(result) == 2
        assert "Use the new API endpoint" in result[0]

    def test_get_maintainer_guidance_rfc_keywords(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "rjmurillo"},
            "body": "This implementation MUST handle edge cases properly.",
        }]
        result = mod._get_maintainer_guidance(comments, ["rjmurillo"])
        assert len(result) >= 1

    def test_get_maintainer_guidance_no_maintainer_comments(self, _import_module):
        mod = _import_module
        comments = [{"user": {"login": "other"}, "body": "hello"}]
        result = mod._get_maintainer_guidance(comments, ["rjmurillo"])
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
        result = mod._get_coderabbit_plan(comments, patterns)
        assert result is not None
        assert "Do X then Y" in result["implementation"]

    def test_get_coderabbit_plan_no_comments(self, _import_module):
        mod = _import_module
        result = mod._get_coderabbit_plan([], {
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
        result = mod._get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result["priority"] == "P1"
        assert result["category"] == "bug"

    def test_get_ai_triage_info_plain_format(self, _import_module):
        mod = _import_module
        comments = [{
            "user": {"login": "bot"},
            "body": "<!-- AI-ISSUE-TRIAGE -->\nPriority: P2\nCategory: enhancement",
        }]
        result = mod._get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result["priority"] == "P2"

    def test_get_ai_triage_info_no_marker(self, _import_module):
        mod = _import_module
        comments = [{"user": {"login": "x"}, "body": "nothing here"}]
        result = mod._get_ai_triage_info(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result is None


class TestHasSynthesizableContent:
    def test_with_guidance(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content(["item"], None, None) is True

    def test_with_triage(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content(
            [], None, {"priority": "P1", "category": None}
        ) is True

    def test_with_coderabbit_implementation(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content(
            [], {"implementation": "do X", "related_issues": [], "related_prs": []},
            None,
        ) is True

    def test_empty(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content([], None, None) is False

    def test_triage_with_none_values(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content(
            [], None, {"priority": None, "category": None}
        ) is False

    def test_empty_plan(self, _import_module):
        mod = _import_module
        assert mod._has_synthesizable_content(
            [], {"implementation": None, "related_issues": [], "related_prs": []},
            None,
        ) is False


class TestBuildSynthesisComment:
    def test_includes_marker_and_copilot(self, _import_module):
        mod = _import_module
        body = mod._build_synthesis_comment(
            "<!-- MARKER -->", ["guidance item"], None, None,
        )
        assert "<!-- MARKER -->" in body
        assert "@copilot" in body
        assert "guidance item" in body

    def test_includes_ai_triage(self, _import_module):
        mod = _import_module
        body = mod._build_synthesis_comment(
            "<!-- M -->", [],
            None, {"priority": "P0", "category": "bug"},
        )
        assert "**Priority**: P0" in body
        assert "**Category**: bug" in body


class TestFindExistingSynthesis:
    def test_found(self, _import_module):
        mod = _import_module
        comments = [{"id": 1, "body": "<!-- MARKER -->\ntext"}]
        result = mod._find_existing_synthesis(comments, "<!-- MARKER -->")
        assert result is not None
        assert result["id"] == 1

    def test_not_found(self, _import_module):
        mod = _import_module
        result = mod._find_existing_synthesis([], "<!-- MARKER -->")
        assert result is None


class TestInvokeCopilotAssignment:
    """Integration tests for invoke_copilot_assignment.main."""

    def test_help_does_not_crash(self, _import_module):
        mod = _import_module
        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0
