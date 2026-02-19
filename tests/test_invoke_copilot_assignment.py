"""Tests for invoke_copilot_assignment.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("invoke_copilot_assignment")
main = _mod.main
_has_content = _mod._has_synthesizable_content
_build_comment = _mod._build_synthesis_comment
_get_guidance = _mod._get_maintainer_guidance
_get_triage = _mod._get_ai_triage_info
_extract_yaml_list = _mod._extract_yaml_list


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _issue_json():
    return json.dumps({
        "title": "Test Issue",
        "body": "Description",
        "labels": [{"name": "bug"}],
    })


def _comments_json(marker: str | None = None, maintainer: str | None = None):
    comments = []
    if marker:
        comments.append({"id": 10, "body": f"{marker}\n\nSynthesis", "user": {"login": "bot"}})
    if maintainer:
        comments.append({"id": 20, "body": maintainer, "user": {"login": "testuser"}})
    return json.dumps(comments)


def _test_config():
    """Return a populated config for tests that need to bypass empty-config validation."""
    return {
        "trusted_sources": {
            "maintainers": ["testuser"],
            "ai_agents": ["bot"],
        },
        "extraction_patterns": {
            "coderabbit": {
                "username": "coderabbitai[bot]",
                "implementation_plan": "## Implementation",
                "related_issues": "Similar Issues",
                "related_prs": "Related PRs",
            },
            "ai_triage": {
                "marker": "<!-- AI-ISSUE-TRIAGE -->",
            },
        },
        "synthesis": {
            "marker": "<!-- COPILOT-CONTEXT-SYNTHESIS -->",
        },
    }


class TestExtractYamlList:
    def test_extracts_items(self):
        content = "maintainers:\n  - alice\n  - bob\nnext_key: val"
        assert _extract_yaml_list(content, "maintainers") == ["alice", "bob"]

    def test_stops_at_next_key(self):
        content = "ai_agents:\n  - bot1[bot]\n  - bot2[bot]\ncoderabbit:"
        result = _extract_yaml_list(content, "ai_agents")
        assert result == ["bot1[bot]", "bot2[bot]"]

    def test_missing_key_returns_empty(self):
        assert _extract_yaml_list("other: val", "maintainers") == []

    def test_handles_inline_comments(self):
        content = "agents:\n  - foo # comment\n  - bar"
        assert _extract_yaml_list(content, "agents") == ["foo # comment", "bar"]

    def test_stops_at_comment_line(self):
        content = "maintainers:\n  - alice\n# end section\nnext: val"
        assert _extract_yaml_list(content, "maintainers") == ["alice"]


class TestHasSynthesizableContent:
    def test_empty(self):
        assert _has_content([], None, None) is False

    def test_with_guidance(self):
        assert _has_content(["Do this"], None, None) is True

    def test_with_triage(self):
        assert _has_content([], None, {"priority": "P1", "category": None}) is True

    def test_with_empty_triage(self):
        assert _has_content([], None, {"priority": None, "category": None}) is False

    def test_with_coderabbit(self):
        plan = {"implementation": "Do something", "related_issues": [], "related_prs": []}
        assert _has_content([], plan, None) is True


class TestBuildSynthesisComment:
    def test_basic(self):
        body = _build_comment("<!-- MARKER -->", ["Fix the bug"], None, None)
        assert "<!-- MARKER -->" in body
        assert "@copilot" in body
        assert "Fix the bug" in body

    def test_with_all_context(self):
        triage = {"priority": "P1", "category": "bug"}
        plan = {"implementation": "Step 1", "related_issues": ["#10"], "related_prs": ["#20"]}
        body = _build_comment("<!-- M -->", ["Guidance"], plan, triage)
        assert "P1" in body
        assert "#10" in body
        assert "#20" in body
        assert "Step 1" in body


class TestGetMaintainerGuidance:
    def test_extract_bullets(self):
        comments = [
            {"body": "- Fix the login flow\n- Update the tests", "user": {"login": "testuser"}}
        ]
        result = _get_guidance(comments, ["testuser"])
        assert len(result) == 2
        assert "Fix the login flow" in result[0]

    def test_extract_rfc_keywords(self):
        comments = [
            {"body": "This MUST be done before release.", "user": {"login": "testuser"}}
        ]
        result = _get_guidance(comments, ["testuser"])
        assert len(result) == 1

    def test_no_maintainer_comments(self):
        comments = [
            {"body": "Some text", "user": {"login": "random"}}
        ]
        result = _get_guidance(comments, ["testuser"])
        assert result == []


class TestGetAITriageInfo:
    def test_table_format(self):
        comments = [
            {
                "body": (
                    "<!-- AI-ISSUE-TRIAGE -->\n"
                    "| **Priority** | `P1` |\n"
                    "| **Category** | `bug` |"
                ),
                "user": {"login": "bot"},
            }
        ]
        result = _get_triage(comments, "<!-- AI-ISSUE-TRIAGE -->")
        assert result["priority"] == "P1"
        assert result["category"] == "bug"

    def test_no_triage(self):
        result = _get_triage([], "<!-- AI-ISSUE-TRIAGE -->")
        assert result is None


@patch("subprocess.run")
def test_empty_config_fails_fast(mock_run):
    """When no copilot-synthesis.yml exists, main exits with code 1."""
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout="/tmp\n"),  # git rev-parse (config loader)
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue-number", "1"])
    assert exc_info.value.code == 1


@patch("subprocess.run")
def test_issue_not_found(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1, stderr="Not Found"),  # issue fetch
    ]

    with patch.object(_mod, "_load_synthesis_config", return_value=_test_config()):
        with pytest.raises(SystemExit) as exc_info:
            main(["--issue-number", "999"])
    assert exc_info.value.code == 2


@patch("subprocess.run")
def test_dry_run_no_content(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=_issue_json()),  # issue fetch
    ]

    with patch.object(_mod, "_load_synthesis_config", return_value=_test_config()):
        with patch.object(_mod, "get_issue_comments", return_value=[]):
            with patch.object(_mod, "get_trusted_source_comments", return_value=[]):
                rc = main(["--issue-number", "1", "--dry-run"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "SKIP" in out


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from text that may contain plain text lines."""
    lines = text.strip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("{"):
            result: dict = json.loads("\n".join(lines[i:]))
            return result
    raise ValueError(f"No JSON object found in: {text!r}")


@patch("subprocess.run")
def test_prepare_context_only(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=_issue_json()),  # issue fetch
    ]

    with patch.object(_mod, "_load_synthesis_config", return_value=_test_config()):
        with patch.object(_mod, "get_issue_comments", return_value=[]):
            with patch.object(_mod, "get_trusted_source_comments", return_value=[]):
                rc = main(["--issue-number", "1", "--prepare-context-only"])

    assert rc == 0
    output = _extract_json(capsys.readouterr().out)
    assert "context_file" in output
    assert output["existing_synthesis_id"] is None
